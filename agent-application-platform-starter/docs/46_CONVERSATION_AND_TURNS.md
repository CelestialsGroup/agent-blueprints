# Conversation and Turn Model

## Ownership

Agent Platform owns AgentConversation, ConversationMessage, branch identity, conversation-local sequence, Conversation Workspace and the WorkOrders created for turns. Business owns the User, Organization, Membership and the authority to mint each ExecutionGrant.

```text
Business User
 -> AgentConversation
    -> immutable ConversationMessage[]
    -> ConversationBranch[] (head, fork point, active WorkOrder, CAS version)
    -> durable Workspace
    -> WorkOrder[] (one executable turn each)
       -> AgentRun / Invocation / Artifact / Recording
```

One-shot Scenario calls create an implicit Conversation in the same admission transaction, so batch clients do not need a separate interaction model.

Conversation lifecycle is governed by `contracts/state-machines/conversation-v1.json`: archive is reversible, deletion is a confirmed irreversible tombstone, and lifecycle timestamps are auditable.

## Turn transaction

`POST /v1/conversations/{id}/turns` atomically:

1. locks Conversation and validates WorkSession, fresh ExecutionGrant and CommercialAuthorizationSnapshot;
2. verifies `client_message_id`, parent, branch and Experience selections;
3. appends the immutable user Message and allocates `message_sequence`;
4. creates one WorkOrder referencing the same Conversation/Turn/Message;
5. writes Workflow Start Outbox and Canonical Events;
6. commits before returning 202.

Same idempotency key, message ID and request digest returns the original Turn. Any mismatch returns 409.

## Branch and concurrency

- `parent_message_id` always references a prior immutable Message.
- A branch can fork from a Message without copying prior messages.
- `ConversationBranch` is the queryable branch-head projection; the Conversation aggregate does not carry a single global active WorkOrder.
- By default only one mutating WorkOrder is active per Conversation branch.
- `interrupt_and_enqueue` records cancellation intent for the active WorkOrder; it never treats intent as cancellation proof.
- Parallel branches use independent WorkOrders and Sandbox slots but share immutable Conversation history.

## Context and memory

Conversation history is not the model prompt. A versioned Context Builder capability selects Messages, Artifacts and summaries under budget and policy. Long-term memory, retrieval or summarization are Providers and their exact revisions are captured in RunManifest.

## Session authorization

WorkSession is Conversation-bound and can optionally narrow to one WorkOrder. Each executable follow-up still requires a fresh Business-issued ExecutionGrant; a browser session never becomes an unlimited commercial authorization.
