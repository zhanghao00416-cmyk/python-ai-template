Classify the following user input into one or more categories.

Categories: qa, task, chat, retrieve_only

Rules:
- "qa": Knowledge Q&A requiring retrieval from knowledge base
- "task": Multi-step task requiring tools or agent execution
- "chat": Free conversation, greetings, small talk, no retrieval needed
- "retrieve_only": Pure retrieval request, no answer generation needed

{{#if candidates}}
Only consider these categories: {{candidates}}
{{/if}}

User input: {{query}}

Respond in JSON format:
{"primary_intent": "<category>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>", "sub_intents": [{"intent": "<category>", "query": "<reconstructed full question>", "original_query": "<original fragment>", "confidence": <0.0-1.0>}], "query": "<reconstructed full query for primary intent>"}
