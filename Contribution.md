# Contribution.md — Group Submission

> **CS 5588 — Week 6 Hands-On Assignment**
> **Team:** Salman Mirza, Amy Ngo, Nithin Songala

---

## Team Contributions (Equal Share)

All three team members contributed equally to the Week 6 deliverables. Work was distributed across design, implementation, integration, and documentation.

---

### Salman Mirza

- **Agent architecture & tool implementation:** Designed and implemented the agent module structure; authored `agent/tools.py` (5 callable tools) and `agent/tool_schemas.py` (declarative tool definitions)
- **Agent runner:** Core logic in `agent/agent_runner.py` — intent detection, tool execution, dual-mode (LLM + rule-based) operation
- **Documentation:** `task1_antigravity_report.md` (Cursor IDE setup and reflection)
- **GitHub:** [SalmanM1/CS5588Week6](https://github.com/SalmanM1/CS5588Week6)

---

### Amy Ngo

- **Agent Chat interface:** Built `src/frontend/pages/agent_chat.py` — chat-style UI, message history, reasoning display, tool results panel
- **Application integration:** Updated `src/frontend/app.py` with Agent Chat navigation; ensured seamless flow between Safety Chat, Agent Chat, and Signal Heatmap
- **UI/UX:** Styling, session state management, and user experience for the agent interaction flow
- **GitHub:** [SalmanM1/CS5588Week6](https://github.com/SalmanM1/CS5588Week6)

---

### Nithin Songala

- **Evaluation & reporting:** Authored `task4_evaluation_report.md` — 3 evaluation scenarios (simple, moderate, complex), performance analysis, limitations, and recommendations
- **README & documentation:** Updated `README.md` with Week 6 architecture, agent tools table, setup instructions, and repository structure
- **Testing & validation:** Verified agent behavior across scenarios; contributed to evaluation design and demo flow
- **GitHub:** [SalmanM1/CS5588Week6](https://github.com/SalmanM1/CS5588Week6)

---

## Shared Reflection

### What We Learned

1. **Tool design matters:** Each tool needs a clear scope and predictable inputs/outputs so the agent can reason about when to use it.
2. **Dual-mode architecture:** LLM mode (Gemini) improves natural-language understanding; rule-based fallback ensures reliability without API keys.
3. **Transparency builds trust:** Exposing reasoning steps and tool results in the UI helps users verify how answers are produced.

### Challenges

- Multi-intent query routing in rule-based mode
- Parameter extraction from natural language (better with LLM)
- Streamlit session state for chat history

---

*CS 5588 · Spring 2026 · Week 6 Assignment*
