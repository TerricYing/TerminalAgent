# Git Ops

## Purpose

执行标准 Git 流程：检查、同步、暂存、提交、推送，并输出可审计结果。

## Use When

- 需要完成日常仓库操作。
- 需要对每一步有明确校验与可回溯输出。
- 需要在风险可控前提下处理变更与推送。

## Workflow

1. 先确认当前目录是 Git 仓库。
2. 收集基线状态（分支、变更、远端）。
3. 涉及推送时先同步远端。
4. 审核变更后再暂存。
5. 提交并验证提交结果。
6. 推送并验证同步状态。
7. 输出命令摘要、关键结果与失败建议。

## Guardrails

- 每一步都检查 `exit_code`，失败即停。
- 推送前必须先同步远端。
- 冲突出现时中止并报告，不自动吞并。
- 删除或回退类操作先说明影响范围。
- 历史改写类命令默认禁用。

## Blocked Commands (Default)

- `git reset --hard`
- `git push --force`
- `git push -f`
- `git rebase -i`
- `git clean -fdx`

用户明确授权并说明范围时，才可一次性临时放开。

## Tool Contract

```json
{
  "name": "git_ops",
  "description": "Run safe and auditable git workflows for check, commit, and push.",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "git_command",
        "description": "Execute a git subcommand in current task context.",
        "parameters": {
          "type": "object",
          "properties": {
            "args": {
              "type": "string",
              "description": "Git argument string."
            }
          },
          "required": ["args"]
        }
      }
    }
  ]
}
```
