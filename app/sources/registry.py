from sqlalchemy.dialects.sqlite import insert

from app.models.sources import Source, utcnow

SOURCES = (
    ("smn_pronostico_general", "Pronóstico Meteorológico General", "CONAGUA/SMN", "smn_general", "https://smn.conagua.gob.mx/es/pronosticos/pronosticossubmenu/pronostico-meteorologico-general"),
    ("smn_potencial_tormentas", "Aviso de Potencial de Tormentas", "CONAGUA/SMN", "smn_storms", "https://smn.conagua.gob.mx/es/pronosticos/avisos/aviso-de-potencial-de-tormentas"),
    ("nhc_atlantic_twd", "Atlantic Tropical Weather Discussion", "NOAA/NHC", "nhc_atlantic", "https://www.nhc.noaa.gov/text/MIATWDAT.shtml"),
    ("nhc_eastern_pacific_twd", "Eastern North Pacific Tropical Weather Discussion", "NOAA/NHC", "nhc_pacific", "https://www.nhc.noaa.gov/text/MIATWDEP.shtml"),
)


def initialize_sources(session):
    # SQLite ON CONFLICT also makes simultaneous process initialization safe.
    for key, name, organization, source_type, url in SOURCES:
        session.execute(insert(Source).values(key=key, name=name, organization=organization,
            source_type=source_type, url=url, is_primary=(key == "smn_pronostico_general"), enabled=True)
            .on_conflict_do_update(index_elements=["key"],
                set_={"is_primary": key == "smn_pronostico_general", "updated_at": utcnow()},
                where=Source.is_primary != (key == "smn_pronostico_general")))
    session.commit()
