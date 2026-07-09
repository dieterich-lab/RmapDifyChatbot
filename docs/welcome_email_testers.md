# RMAP Chatbot – Tester-Zugang & Quick Start

Hallo zusammen,

der RMAP Chatbot (v0.4.3) ist jetzt für euch zum Testen bereit. Der Bot beantwortet Fragen zu 84 Papers aus der ersten RMaP-Förderperiode – von RNA-Modifikationen über Nanopore-Sequencing bis zu tRNA-Biologie.

## Zugang

### Published App (stabil, produktiv)
- URL: http://rmap-chatbot-demo-dify.internal/chat/qSKbMGikJuIdhlfr
- Direkt im Browser nutzbar

### Draft-Modus (zum Debuggen)
Ihr bekommt in Kürze eine Einladung zur Dify-Account-Erstellung von Philipp.
Nach dem Login:
1. Öffnet die App "RMAP Chatbot Iterative Retrieval"
2. Wechselt in den Tab **"Preview"** (nicht "Published"!)
3. Gebt eure Query ein – im rechten Panel seht ihr den Workflow-Status jedes Nodes (Laufzeit, Input/Output, Fehler)

## 5 Frage-Typen, die der Bot versteht

| Intent | Beispiel | Erwartete Antwort |
|---|---|---|
| metadata_list | "Papers by Christoph Dieterich" | 6 Papers aufgelistet |
| content_summary | "Summarize them" (nach einer Liste) | Global Synthesis + 3 Bullets/Paper |
| knowledge_retrieval | "What is m6A and how is it detected?" | Methoden mit Paper-Citations |
| author_lookup | "Who has worked on tRNA modifications?" | ~7 Papers mit allen Autoren |
| entity_lookup | "Which RNA modifications are most studied?" | Tabelle: Entity-Typ → Paper |

## Tipps zum Testen

- **Immer im "Preview"-Tab testen** – dort seht ihr, welcher Node wie lange läuft und wo ggf. Fehler auftreten
- **Follow-up-Queries**: "Summarize them" funktioniert nur nach einer metadata_list-Query (der Bot merkt sich die Paper-Liste)
- **Fehleranalyse**: Wenn ein Node rot/blau markiert ist, draufklicken → Input/Output/Fehlermeldung einsehen
- **README**: https://github.com/dieterich-lab/RmapDifyChatbot – Architektur-Diagramm und Node-Referenz

## Bekannte Limits (v0.4.3)

- author_lookup/entity_lookup: Retrieval-Qualität hängt von PubMed-Metadaten-Coverage ab (83%)
- knowledge_retrieval: ~5 Methoden/Paper, gelegentlich Retrieval-Ranking-Issues
- Kein Multilingual-Support – englische Queries liefern die besten Ergebnisse

Bei Fragen oder wenn eine Query unerwartete Ergebnisse liefert, schreibt mir einfach – am besten mit Conversation-ID und Screenshot aus dem Preview-Tab.

Viel Spaß beim Testen!
Philipp
