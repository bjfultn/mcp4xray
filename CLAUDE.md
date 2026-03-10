# X-ray Astronomy Archive MCP Project

## Project Goal

Build a multi-mission X-ray astronomy archive assistant using MCP (Model Context Protocol) servers. The assistant should allow a researcher to query and explore the **Chandra** and **XMM-Newton** archives, retrieve documentation, and eventually support cross-mission science queries — all from a single frontend/agent interface.

---

## Architecture Decision

### Pattern: Shared System Prompt + Per-Mission Resource Servers

After evaluating several approaches, the chosen architecture is:

- **One shared system prompt** — establishes the assistant as a general X-ray astronomy archive expert, aware of both missions, familiar with general query conventions
- **Per-mission MCP servers** — each server exposes mission-specific tools and documentation as *resources*, not personality prompts
- **All servers connected simultaneously** — the agent routes to the appropriate tools/resources based on query context, enabling cross-mission queries in a single session

This avoids the "personality conflict" problem that arises when multiple MCP servers each try to own the system prompt.

---

## Planned MCP Servers

### `chandra-mcp`
- Tools for querying the Chandra Source Catalog and archive (CSC, CXC)
- Resources: Chandra-specific documentation, instrument descriptions (ACIS, HRC), proposal/observation metadata
- Possible APIs: [CXC archive](https://cxc.harvard.edu/), CSCview, CIAO documentation

### `xmm-mcp`
- Tools for querying the XMM-Newton Science Archive (XSA)
- Resources: XMM-specific documentation, instrument descriptions (EPIC, RGS, OM), observation metadata
- Possible APIs: [ESA XSA](https://www.cosmos.esa.int/web/xmm-newton/xsa), HEASArc XMM tables

### `xray-docs-mcp` *(optional — may fold into each mission server)*
- Searchable documentation resources for both missions
- Could include proposal guidelines, analysis threads, known caveats
- RAG over mission documentation

---

## Shared System Prompt (Draft)

```
You are an expert X-ray astronomy archive assistant with deep knowledge of 
the Chandra and XMM-Newton observatories. You help researchers query mission 
archives, interpret observation metadata, find relevant sources, and navigate 
mission documentation. When working across missions, you understand the 
differences in instrument capabilities, coordinate conventions, and archive 
interfaces. You prefer precise, scientifically accurate responses and flag 
ambiguities when archive queries could be interpreted multiple ways.
```

---

## Open Questions / Next Decisions

- [ ] Which archive APIs are programmatically accessible vs. require scraping?
- [ ] Authentication requirements for Chandra/XMM archive access?
- [ ] What does the frontend look like — CLI, web UI, or Claude Code itself?
- [ ] Fold docs into each mission server, or keep as a separate `xray-docs-mcp`?
- [ ] Should HEASArc (multi-mission) be a fourth server, or tools within each?
- [ ] RAG strategy for documentation — embed at build time or live retrieval?

---

## Suggested First Steps

1. Prototype `chandra-mcp` with 2-3 basic archive query tools (e.g., cone search, observation lookup by ObsID)
2. Verify the Chandra archive API is queryable programmatically (ADQL/TAP? REST?)
3. Stand up a minimal MCP server using the [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk) or Python SDK
4. Test with Claude Desktop or Claude Code before building a custom frontend
5. Repeat for `xmm-mcp`
6. Add resource endpoints for documentation once tools are working

---

## References

- [MCP Specification](https://modelcontextprotocol.io)
- [MCP TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Chandra X-ray Center](https://cxc.harvard.edu/)
- [XMM-Newton Science Archive](https://www.cosmos.esa.int/web/xmm-newton/xsa)
- [HEASArc](https://heasarc.gsfc.nasa.gov/) — may be useful for cross-mission queries
