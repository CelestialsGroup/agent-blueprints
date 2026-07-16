# 状态机规范

所有状态变化必须通过领域命令或已验证事件执行，禁止直接更新 `status` 字段。

## 1. WorkOrder

终态：

- completed
- partial
- failed
- cancelled

`partial`：主交付物已经产生，但一个或多个调用方声明的 required delivery format 未完成。

| From | Command/Event | Guard | To |
|---|---|---|---|
| accepted | enqueue | admission committed | queued |
| accepted | request_cancel | cancellable | cancelled |
| queued | start | capacity available | running |
| queued | request_cancel | cancellable | cancelled |
| running | wait | external signal required | waiting |
| running | pause | pausable | paused |
| running | finish | all required outputs ready | completed |
| running | finish_partial | primary ready, required derivative failed | partial |
| running | fail | unrecoverable | failed |
| running | request_cancel | cancellable | cancel_requested |
| waiting | signal | valid signal | running |
| waiting | pause | pausable | paused |
| waiting | request_cancel | cancellable | cancel_requested |
| paused | resume | valid | running |
| paused | request_cancel | cancellable | cancel_requested |
| cancel_requested | begin_cancel | execution active | cancelling |
| cancel_requested | confirm_cancel | no active execution | cancelled |
| cancelling | cancel_complete | resources settled | cancelled |
| cancelling | deliver_partial | primary artifact retained | partial |
| cancelling | fail | cleanup failed irrecoverably | failed |

## 2. Invocation

Invocation 表示一个稳定逻辑副作用，多个 Attempt 属于同一个 Invocation。

| From | Command/Event | Guard | To |
|---|---|---|---|
| prepared | dispatch_attempt | budget and policy allow | executing |
| executing | attempt_succeeded | current fencing token | succeeded |
| executing | attempt_failed_retryable | retry policy has capacity | retry_scheduled |
| retry_scheduled | retry_due | deadline valid | executing |
| executing | attempt_failed_terminal | known terminal failure | failed |
| executing | attempt_outcome_unknown | result cannot be confirmed | outcome_unknown |
| outcome_unknown | reconcile_start | reconciler available | reconciling |
| reconciling | confirmed_success | evidence sufficient | succeeded |
| reconciling | confirmed_failure | evidence sufficient | failed |
| reconciling | reconciliation_timeout | deadline exceeded | manual_review |
| outcome_unknown | reconciliation_timeout | deadline exceeded | manual_review |
| manual_review | resolve_success | authorized operator and evidence | succeeded |
| manual_review | resolve_failure | authorized operator and evidence | failed |
| manual_review | abandon | explicit risk acceptance | abandoned |
| prepared/executing/retry_scheduled | request_cancel | cancellable | cancel_requested |
| cancel_requested | cancel_confirmed | current operation stopped | cancelled |
| cancel_requested | result_success | operation already succeeded | succeeded |

规则：

- `failed_retryable` 是 Attempt 状态，不是 Invocation 终态。
- 新 Attempt 使用同一 Invocation ID、递增 Attempt Number 和 Fencing Token。
- `outcome_unknown` 禁止直接创建新 Attempt。
- `abandoned` 是明确审计的终态，不能等价成 failed。
- Manual Review 必须保存 Evidence、Operator、Decision、Reason 和 Timestamp。

## 3. InvocationAttempt

| From | Event | To |
|---|---|---|
| accepted | provider_started | running |
| accepted/running | confirmed_success | succeeded |
| accepted/running | retryable_failure | failed_retryable |
| accepted/running | terminal_failure | failed_terminal |
| accepted/running | uncertain_timeout | outcome_unknown |
| accepted/running | request_cancel | cancel_requested |
| cancel_requested | cancel_confirmed | cancelled |
| accepted/running | superseded_by_new_fence | superseded |

Attempt 为不可变历史。任何后续重试都创建新的 Attempt 记录。

## 4. Plugin Invocation Status Projection

合法组合：

```text
accepted/running/cancelled
  不携带 result/error

succeeded
  必须携带 result，禁止携带 error

failed
  必须携带 known_failed error，禁止携带 result

outcome_unknown
  必须携带 outcome_unknown error，禁止携带 result
```

该约束由 `plugin-invocation-status.schema.json` 的条件 Schema 强制。

## 5. EditSession

| From | Event | To |
|---|---|---|
| active | begin_commit | committing |
| committing | commit_success | committed |
| committing | version_conflict | conflicted |
| conflicted | rebase | active |
| active/conflicted | discard | discarded |
| active/conflicted | expire | expired |

## 6. Sandbox

| From | Command/Event | Guard | To |
|---|---|---|---|
| requested | provision | valid Spec and capacity | provisioning |
| provisioning | backend_ready | generation current | ready |
| provisioning | fail | unrecoverable | failed |
| ready | suspend | capability supported | suspending |
| suspending | suspended | generation current | suspended |
| suspended | resume | lease valid | resuming |
| resuming | ready | generation current | ready |
| ready/suspended | terminate | valid fencing | terminating |
| terminating | backend_deleted | cleanup complete | terminated |
| ready/suspended | lease_expired | no extension | expired |
| * | provider_failure | unrecoverable | failed |

## 7. SandboxOperation

| From | Event | To |
|---|---|---|
| accepted | dispatch | running |
| running | confirmed_success | succeeded |
| running | confirmed_failure | failed |
| running | uncertain_timeout | outcome_unknown |
| running | request_cancel | cancel_requested |
| cancel_requested | cancelled | cancelled |
| cancel_requested | confirmed_success | succeeded |

Sandbox desired state 与 observed state 分开；平台通过 Generation、Attempt 和 Fencing 验证 Provider 更新。
