# Archived experiments

These files are retained as historical source, not active application entry points.
Their contents are unchanged. They may require old data, packages, or original
working-directory assumptions to run.

| Original path | Archived path | Reason |
| --- | --- | --- |
| Map.py | legacy/Map.py | Standalone Folium prototype; not referenced by the current app. |
| Test.py | legacy/Test.py | Earlier embedded-template map builder; current builder is APP.py. |
| main.py | legacy/main.py | Standalone diagnostic using older dataset names and graph API. |
| models/graph.py | legacy/models/graph.py | Earlier graph experiment; current app imports models.bwca_graph. |

A repository-wide reference check found no active imports or calls to these files.
The processing scripts and raw datasets remain in their original locations because
absence from APP.py does not establish that they are obsolete.
