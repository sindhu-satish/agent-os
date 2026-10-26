export type AgentPreset = {
  id: string;
  name: string;
  slugPrefix: string;
  description: string;
  systemPrompt: string;
  toolNames: string[];
  sampleTask: string;
  blurb: string;
};

export const AGENT_PRESETS: AgentPreset[] = [
  {
    id: "calculator",
    name: "Calculator",
    slugPrefix: "calc",
    description: "Single-tool arithmetic with add.",
    systemPrompt: "Add numbers with the add tool.",
    toolNames: ["add"],
    sampleTask: "add 2 and 3",
    blurb: "One tool call → result 5",
  },
  {
    id: "multiplier",
    name: "Multiplier",
    slugPrefix: "mult",
    description: "Single-tool arithmetic with multiply.",
    systemPrompt: "Multiply numbers with the multiply tool.",
    toolNames: ["multiply"],
    sampleTask: "multiply 6 by 7",
    blurb: "One tool call → result 42",
  },
  {
    id: "math-pipeline",
    name: "Math pipeline",
    slugPrefix: "pipeline",
    description: "Chains add then multiply across two tool steps.",
    systemPrompt: "Add first, then multiply the sum.",
    toolNames: ["add", "multiply"],
    sampleTask: "add 2 and 3 then multiply by 4",
    blurb: "Two tools in sequence → result 20",
  },
  {
    id: "greeter",
    name: "Greeter",
    slugPrefix: "greeter",
    description: "Builds a greeting with concat.",
    systemPrompt: "Greet people by concatenating Hello with their name.",
    toolNames: ["concat"],
    sampleTask: "greet Ada Lovelace",
    blurb: "Concat tool → Hello, Ada Lovelace",
  },
  {
    id: "announcer",
    name: "Announcer",
    slugPrefix: "announce",
    description: "Repeats a message through echo.",
    systemPrompt: "Echo the requested message.",
    toolNames: ["echo"],
    sampleTask: "say AgentOS is durable",
    blurb: "Echo tool → same message back",
  },
  {
    id: "fact-finder",
    name: "Fact finder",
    slugPrefix: "facts",
    description: "Looks up canned facts.",
    systemPrompt: "Look up facts with the lookup tool.",
    toolNames: ["lookup"],
    sampleTask: "lookup capital of france",
    blurb: "Lookup → Paris",
  },
  {
    id: "research-noter",
    name: "Research noter",
    slugPrefix: "research",
    description: "Looks up a fact, then echoes a note about it.",
    systemPrompt: "Research a topic, then note the finding with echo.",
    toolNames: ["lookup", "echo"],
    sampleTask: "research capital of france and note it",
    blurb: "Lookup then echo → Note: Paris",
  },
];
