# Automation Ops

## Purpose

执行自动化编排任务，组合 Shell 与 Git 完成“条件检查 -> 动作执行 -> 结果汇总”的流程。

## Use When

- 需要定时触发或轮询检查。
- 需要根据条件分支执行后续动作。
- 需要串联进程检查、Git 同步、提交推送和收尾动作。

## Workflow

1. 创建或确认自动化触发条件。
2. 先做只读检查，再做变更动作。
3. 若前置条件不满足，延后并结束当前轮。
4. 若条件满足，执行 Git 流程并验证结果。
5. 所有步骤都检查 `exit_code`，失败即停。
6. 输出完整执行摘要与失败点。

## Guardrails

- 关机、重启、强制终止等高风险动作必须有明确授权。
- Git 冲突、推送失败、权限错误时必须中止并报告。
- 允许在工作区外执行命令。
- 若仅为辅助执行而临时创建脚本，默认写入当前任务工作区，不写入仓库根目录或外部绝对路径。

## Blocked Commands (Default)

- `git reset --hard`
- `git push --force`
- `git push -f`
- `git clean -fdx`

用户明确授权并说明范围时，才可一次性临时放开。

## Tool Contract

```json
{
  "name": "automation_ops",
  "description": "Automate condition-based operational workflows across shell and git.",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_shell_command",
        "description": "Execute shell commands for checks, scheduling, and system operations.",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string",
              "description": "Command string to run."
            }
          },
          "required": ["command"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "git_command",
        "description": "Execute git subcommands for check, commit, and push flows.",
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