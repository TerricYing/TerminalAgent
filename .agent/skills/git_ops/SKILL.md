# Git Ops Skill

## 描述

完整 Git 操作规范 skill。用于状态检查、分支管理、同步、提交、推送与安全回滚边界控制。

## 适用场景

- 需要执行完整的 Git 日常流程（检查、分支、提交、推送）
- 需要在执行前后有明确校验与安全边界
- 需要对风险命令做约束，避免破坏历史

## 调用流程

1. 仓库确认
   1. 执行 `git rev-parse --is-inside-work-tree`。
   2. 若非仓库，立即返回错误并停止。

2. 基线检查
   1. 执行 `git status --short`。
   2. 执行 `git branch --show-current`。
   3. 必要时执行 `git remote -v`、`git log --oneline -10`。

3. 同步远端（若涉及推送）
   1. 执行 `git fetch --all --prune`。
   2. 如目标分支存在上游，先 `git pull --rebase`。
   3. 若出现冲突，停止并返回冲突文件信息。

4. 变更确认与暂存
   1. 先用 `git diff --stat` / `git diff` 审核变更。
   2. 再执行 `git add -A` 或按需 `git add <path>`。
   3. 执行 `git status --short` 二次确认暂存结果。

5. 提交
   1. 使用明确提交信息：`git commit -m "<message>"`。
   2. 提交后执行 `git log --oneline -1` 验证提交成功。

6. 推送
   1. 执行 `git push`（或首次 `git push -u origin <branch>`）。
   2. 推送后执行 `git status -sb` 验证是否已同步。

7. 结束输出
   1. 汇总本次执行命令与关键结果。
   2. 若失败，输出失败步骤、错误信息、下一步建议。

## 注意事项

- 每一步都必须检查 `exit_code`，失败即停，不允许盲目继续。
- 推送前必须先同步远端，避免直接覆盖他人变更。
- 禁止执行高风险历史改写命令，除非用户明确授权。
- 对删除/回退类操作必须先给出影响范围说明。
- 不得自动处理冲突并继续；冲突出现时必须中止并报告。

## 禁用命令（默认）

- `git reset --hard`
- `git push --force`
- `git push -f`
- `git rebase -i`
- `git clean -fdx`

如用户明确授权并说明范围，才可在一次性任务中临时执行。

```json
{
  "name": "git_ops",
  "description": "完整 Git 操作规范 skill。用于状态检查、分支管理、同步、提交、推送与安全回滚边界控制。",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "git_command",
        "description": "在当前任务工作区执行 git 子命令。",
        "parameters": {
          "type": "object",
          "properties": {
            "args": {
              "type": "string",
              "description": "git 参数字符串，例如 'status --short'、'fetch --all --prune'、'commit -m \"msg\"'。"
            }
          },
          "required": ["args"]
        }
      }
    }
  ]
}
```
