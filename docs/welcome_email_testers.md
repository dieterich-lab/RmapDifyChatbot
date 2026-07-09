# RMAP Chatbot – Tester Access & Quick Start

Hi everyone,

the RMAP Chatbot (v0.4.3) is ready for testing. It answers questions about 84 papers from the first RMaP funding period – spanning RNA modifications, nanopore sequencing, and tRNA biology.

## Access

### Published App (stable, production)
- URL: http://rmap-chatbot-demo-dify.internal/chat/qSKbMGikJuIdhlfr
- Ready to use – just open in your browser

### Draft Mode (for debugging)
You'll receive a Dify account invitation from Philipp shortly.
After logging in:
1. Open the app **"RMAP Chatbot Iterative Retrieval"**
2. Switch to the **"Preview"** tab (NOT "Published"!)
3. Enter your query – the right-hand panel shows each node's status (runtime, input/output, errors)

## 5 Query Types the Bot Understands

| Intent | Example Query | Expected Answer |
|---|---|---|
| `metadata_list` | "Papers by Christoph Dieterich" | 6 papers listed with title, year, journal |
| `content_summary` | "Summarize them" (after a list query) | Global synthesis + 3 bullet points per paper |
| `knowledge_retrieval` | "What is m6A and how is it detected?" | Methods with full paper citations (all authors) |
| `author_lookup` | "Who has worked on tRNA modifications?" | ~7 papers with all authors + verbatim quotes |
| `entity_lookup` | "Which RNA modifications are most studied?" | Table: entity → type → source paper |

## Testing Tips

- **Always test in the "Preview" tab** – you'll see exactly which node takes how long and where errors occur
- **Follow-up queries**: "Summarize them" only works right after a `metadata_list` query (the bot remembers the paper list)
- **Debugging**: Click on any red/blue node → view its input, output, and error message
- **Known UI glitch**: The workflow editor shows 20 "not connected" warnings – this is a Dify UI bug, the actual graph is correct and fully functional
- **English queries** produce the best results

## Known Limits (v0.4.3)

- **author_lookup / entity_lookup**: Retrieval quality depends on PubMed metadata coverage (currently 83%)
- **knowledge_retrieval**: ~5 methods per paper; occasional retrieval ranking issues
- **No multilingual support** – English queries yield the best results

## Reporting Issues

If a query returns unexpected results, please send me:
- The **Conversation ID** (shown at the top of the Preview panel)
- A **screenshot** from the Preview tab showing the node status
- The **exact query** you used

## Resources

- **README**: https://github.com/dieterich-lab/RmapDifyChatbot – architecture diagram & node reference
- **CHANGELOG**: https://github.com/dieterich-lab/RmapDifyChatbot/blob/master/CHANGELOG.md

Happy testing!
Philipp
