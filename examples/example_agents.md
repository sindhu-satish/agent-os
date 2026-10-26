# Example agents

These prompts work with the scripted provider and the seeded builtin tools. Create the agent with the listed `tool_names`, then submit the sample task text.

| Agent | Tools | Sample task | Expected result |
| --- | --- | --- | --- |
| Calculator | `add` | `add 2 and 3` | `5` |
| Multiplier | `multiply` | `multiply 6 by 7` | `42` |
| Math pipeline | `add`, `multiply` | `add 2 and 3 then multiply by 4` | `20` (two tool steps) |
| Greeter | `concat` | `greet Ada Lovelace` | `Hello, Ada Lovelace` |
| Announcer | `echo` | `say AgentOS is durable` | `AgentOS is durable` |
| Fact finder | `lookup` | `lookup capital of france` | `Paris` |
| Research noter | `lookup`, `echo` | `research capital of france and note it` | `Note: Paris` (two tool steps) |

Lookup topics known to the scripted tool: `capital of france`, `population of tokyo`, `boiling point of water`, `speed of light`.

Crash recovery in the dashboard still seeds the calculator-style `add 2 and 3` path.
