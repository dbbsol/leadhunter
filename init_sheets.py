"""Administração por linha de comando (sem precisar abrir o app).

  python init_sheets.py add --email cliente@gmail.com --nome "Maria" --tenant-sheet-id <ID> [--plano Pro] [--dias 30] [--limite 300]
  python init_sheets.py renovar --email cliente@gmail.com --dias 30
  python init_sheets.py suspender --email cliente@gmail.com
  python init_sheets.py reativar --email cliente@gmail.com
  python init_sheets.py listar
  python init_sheets.py estrutura --tenant-sheet-id <ID>      # só cria abas/cabeçalhos
"""
import argparse
from datetime import date, timedelta

from scripts._common import G, R, X, explain_google_error, gspread_client, load_secrets

s = load_secrets()
gc = gspread_client(s)
client_email = s["gcp_service_account"].get("client_email", "")

from core.permissions import parse_date  # noqa: E402
from integrations.google_sheets import SheetsStore  # noqa: E402
from integrations.storage import ADMIN_SCHEMA, TENANT_SCHEMA  # noqa: E402


def admin_store():
    st = SheetsStore(gc, s["ADMIN_SHEET_ID"], ADMIN_SCHEMA)
    st.ensure_schema()
    return st


def find(st, email):
    return next((r for r in st.all("ASSINATURAS", fresh=True) if r["email"].lower() == email.lower()), None)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("--email", required=True)
    a.add_argument("--nome", default="")
    a.add_argument("--tenant-sheet-id", required=True)
    a.add_argument("--plano", default="Pro")
    a.add_argument("--dias", type=int, default=30)
    a.add_argument("--limite", type=int, default=300)
    r = sub.add_parser("renovar")
    r.add_argument("--email", required=True)
    r.add_argument("--dias", type=int, default=30)
    for n in ("suspender", "reativar"):
        sub.add_parser(n).add_argument("--email", required=True)
    sub.add_parser("listar")
    e = sub.add_parser("estrutura")
    e.add_argument("--tenant-sheet-id", required=True)
    args = p.parse_args()

    try:
        st = admin_store()
        if args.cmd == "add":
            tid = args.tenant_sheet_id.strip()
            created = SheetsStore(gc, tid, TENANT_SCHEMA).ensure_schema()
            print(f"{G}✔{X} Planilha do cliente pronta (abas criadas: {', '.join(created) or 'já existiam'})")
            st.upsert("CLIENTES", [{"email": args.email.lower(), "nome": args.nome, "empresa": "", "criado_em": date.today().isoformat()}], key="email")
            st.upsert("ASSINATURAS", [{"email": args.email.lower(), "nome": args.nome, "plano": args.plano, "inicio": date.today().isoformat(),
                                       "vencimento": (date.today() + timedelta(days=args.dias)).isoformat(), "status": "ativo",
                                       "limite_pesquisas": args.limite, "consumo": 0, "planilha_id": tid}], key="email")
            print(f"{G}✔{X} {args.email} cadastrado: ativo até {(date.today() + timedelta(days=args.dias)).isoformat()}, limite {args.limite} pesquisas")
        elif args.cmd == "renovar":
            row = find(st, args.email) or exit(f"{R}✘ e-mail não encontrado{X}")
            base = max(parse_date(row.get("vencimento")) or date.today(), date.today())
            novo = (base + timedelta(days=args.dias)).isoformat()
            st.upsert("ASSINATURAS", [{"email": row["email"], "vencimento": novo, "status": "ativo", "consumo": 0}], key="email")
            print(f"{G}✔{X} Renovado até {novo} (consumo zerado)")
        elif args.cmd in ("suspender", "reativar"):
            row = find(st, args.email) or exit(f"{R}✘ e-mail não encontrado{X}")
            st.upsert("ASSINATURAS", [{"email": row["email"], "status": "suspenso" if args.cmd == "suspender" else "ativo"}], key="email")
            print(f"{G}✔{X} {args.email}: {'suspenso' if args.cmd == 'suspender' else 'ativo'}")
        elif args.cmd == "listar":
            for row in st.all("ASSINATURAS", fresh=True):
                print(f"{row['email']:35} {row['status']:9} vence {row['vencimento']:10} consumo {row.get('consumo','0')}/{row.get('limite_pesquisas','')}  plano {row.get('plano','')}")
        elif args.cmd == "estrutura":
            created = SheetsStore(gc, args.tenant_sheet_id.strip(), TENANT_SCHEMA).ensure_schema()
            print(f"{G}✔{X} Estrutura pronta. Criadas: {', '.join(created) or 'nenhuma (já existiam)'}")
    except SystemExit:
        raise
    except Exception as exc:
        exit(f"{R}✘ {explain_google_error(exc, client_email)}{X}")


if __name__ == "__main__":
    main()
