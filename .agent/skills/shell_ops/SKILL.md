# Shell Ops Skill

## 描述

Shell 命令执行 skill。用于进程检查、定时任务、系统命令与诊断操作。

## 适用场景

- 需要执行系统命令（PowerShell/CMD）
- 需要检查进程、服务、系统状态
- 需要创建或管理系统定时任务

## 调用流程

1. 前置确认
   1. 明确目标与影响范围，避免误执行高风险命令。
   2. 优先先做只读检查命令（例如查询进程）再做变更命令。

2. 命令执行
   1. 通过 run_shell_command 执行一条明确命令。
   2. 每次执行后检查 exit_code、stdout、stderr。

3. 失败处理
   1. exit_code 非 0 时，先收敛错误原因，不得盲目重试。
   2. 如需重试，必须说明重试条件与间隔。

4. 结束输出
   1. 汇总执行命令与结果。
   2. 标注失败步骤和下一步建议。

## 注意事项

- 每一步都必须检查 exit_code，失败即停。
- 默认禁止危险系统命令，除非用户明确授权。
- 对删除、关机、重启、杀进程操作必须先说明影响。
- 涉及定时任务时，需输出任务名、触发时间、执行命令。
- 允许到工作区外执行或读取命令，但若只是为了辅助执行而临时创建脚本，默认写入当前任务工作区，不要写到项目根目录或其他外部绝对路径。

## 禁用命令（默认）

- format
- diskpart
- del /f /s /q C:\\*
- shutdown /s /f /t 0
- taskkill /f /im *

如用户明确授权并说明范围，才可在一次性任务中临时执行。

```json
{
  "name": "shell_ops",
  "description": "Shell 命令执行 skill。用于进程检查、定时任务、系统命令与诊断操作。",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_shell_command",
        "description": "在当前任务工作区执行 shell 命令。",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string",
              "description": "要执行的命令字符串，例如 'Get-Process python' 或 'schtasks /Query'。"
            }
          },
          "required": ["command"]
        }
      }
    }
  ]
}
```