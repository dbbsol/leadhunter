"""Testa a busca real de empresas, fora do app. Uso:  python -m scripts.testar_osm"""
import os
import sys

from scripts._common import G, R, X, Y, load_secrets

s = load_secrets()
os.environ["NOMINATIM_CONTACT"] = str(s.get("NOMINATIM_CONTACT", ""))
os.environ["GEOAPIFY_API_KEY"] = str(s.get("GEOAPIFY_API_KEY", ""))
from discovery import osm  # noqa: E402

usando = "Geoapify" if osm.usando_geoapify() else "Overpass"
print("Fonte de busca:", usando if usando == "Geoapify" else "Overpass (GEOAPIFY_API_KEY não preenchida: instável)")
try:
    leads = osm.search_osm("Restaurantes", "Porto Alegre", "RS", 20)
    print(f"{G}✔{X} {usando} devolveu {len(leads)} empresas")
    print(f"   {sum(1 for l in leads if l.get('telefone'))} com telefone · {sum(1 for l in leads if l.get('site'))} com site")
    for l in leads[:8]:
        print("   -", l["nome"], "|", l.get("bairro") or "-", "|", l.get("telefone") or "sem telefone")
    if not leads:
        print(f"{Y}! Nenhuma empresa voltou. Rode de novo ou me mande esta saída.{X}")
except osm.DiscoveryError as exc:
    print(f"{R}✘ {exc}{X}")
    sys.exit(1)
except Exception as exc:
    print(f"{R}✘ Erro inesperado: {type(exc).__name__}: {exc}{X}")
    sys.exit(1)
