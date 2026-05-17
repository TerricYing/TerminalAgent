# Shell Ops

## Purpose

执行通用 Shell 命令（PowerShell/CMD），用于检查、诊断和轻量系统操作。

## Use When

- 需要运行系统命令并读取结果。
- 需要检查进程、服务、任务计划或环境状态。
- 需要在一个步骤内快速完成命令级操作。

## Workflow

1. 先明确目标与影响范围。
2. 优先执行只读命令收集上下文。
3. 执行变更命令前说明影响。
4. 每次命令后检查 `exit_code`、`stdout`、`stderr`。
5. 失败时先解释失败原因，再决定是否重试。
6. 结束时汇总命令、结果与后续建议。

## Guardrails

- 默认不执行高风险破坏命令。
- 删除、关机、重启、强杀进程前必须先说明影响。
- 允许在工作区外执行或读取命令。
- 若仅为辅助执行而临时创建脚本，默认写入当前任务工作区，不写入仓库根目录或外部绝对路径。

## Blocked Commands (Default)

- `format`
- `diskpart`
- `del /f /s /q C:\\*`
- `shutdown /s /f /t 0`
- `taskkill /f /im *`

用户明确授权并说明范围时，才可一次性临时放开。

## Tool Contract

```json
{
  "name": "shell_ops",
  "description": "Run shell commands for diagnostics and controlled system operations.",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_shell_command",
        "description": "Execute one shell command in the current task context.",
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
    }
  ]
}
```