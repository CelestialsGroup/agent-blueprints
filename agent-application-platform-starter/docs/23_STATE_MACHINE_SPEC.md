# 状态机规范

## 1. WorkOrder

终态：

- completed
- partial
- failed
- cancelled

`partial` 定义：主交付物已产生，但一个或多个调用方声明的 required delivery format 未完成。

| From | Command/Event | Guard | To |
|---|---|---|---|
| accepted | enqueue | valid | queued |
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
| cancelling | fail | cancellation cleanup failed irrecoverably | failed |

## 2. Invocation

| From | Event | To |
|---|---|---|
| prepared | dispatch | executing |
| executing | confirmed_success | succeeded |
| executing | confirmed_failure | failed |
| executing | timeout_unknown | outcome_unknown |
| outcome_unknown | reconcile_start | reconciling |
| reconciling | confirmed_success | succeeded |
| reconciling | confirmed_failure | failed |
| prepared/executing | request_cancel | cancel_requested |
| cancel_requested | cancel_confirmed | cancelled |
| cancel_requested | result_success | succeeded |

## 3. EditSession

| From | Event | To |
|---|---|---|
| active | begin_commit | committing |
| committing | commit_success | committed |
| committing | version_conflict | conflicted |
| conflicted | rebase | active |
| active/conflicted | discard | discarded |
| active/conflicted | expire | expired |

所有状态变化必须通过领域方法，禁止直接更新 status 字段。

## 4. Approval

| From | Event | To |
|---|---|---|
| pending | approve | approved |
| pending | reject | rejected |
| pending | expire | expired |
| pending | cancel_work | cancelled |

Decision 使用 Idempotency-Key；终态不可被新的 Decision 覆盖。

## 5. RuntimeSession

| From | Event | To |
|---|---|---|
| creating | route_ready | active |
| creating | route_failed | failed |
| active | revoke | revoked |
| active | expire | expired |
| active | runtime_lost | reconnecting |
| reconnecting | route_ready | active |
| reconnecting | deadline_exceeded | failed |

RuntimeSession 终止不等于 WorkOrder 终止。

## 6. PreviewSession

| From | Event | To |
|---|---|---|
| preparing | render_ready | ready |
| preparing | render_failed | failed |
| ready | expire | expired |


## 5. Sandbox

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

## 6. SandboxOperation

| From | Event | To |
|---|---|---|
| accepted | dispatch | running |
| running | confirmed_success | succeeded |
| running | confirmed_failure | failed |
| running | uncertain_timeout | outcome_unknown |
| running | request_cancel | cancel_requested |
| cancel_requested | cancelled | cancelled |
| cancel_requested | confirmed_success | succeeded |

Sandbox desired state 与 observed state 分开；直接更新 observed state 属于 Provider 行为，平台通过 generation 和 fencing 验证。
