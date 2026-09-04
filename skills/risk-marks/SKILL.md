---
name: risk-marks
description: Use when 客服/申訴 hands over a gamapassID 名單 to unlock (移除黑名單標注 / 移除 risk mark / 解鎖), or when batch-importing GTW 黑名單 risk marks to PROD
allowed-tools: Bash, Read, Write
---

# GAMAPASS 風險標注（risk marks）批次增刪

打的是 gateway admin API `POST/DELETE /v1/admin/auth/riskMarks`。

腳本與留檔在 `~/Gama/tools/script/api-risk-marks/`（**未納版控**，細節看該目錄的
`README.md`）；分析腳本 `prepare_unlock.py` 在本 skill 目錄，是版控過的那份。

| 檔案 | 用途 |
|---|---|
| `<skill>/prepare_unlock.py` | 解鎖名單 openID → 要刪的手機清單＋**這次刪不到什麼**的報告 |
| `~/Gama/tools/.../delete_risk_marks.py` | 移除標注 DELETE |
| `~/Gama/tools/.../import_risk_marks.py` | 新增標注 POST |
| `~/Gama/tools/.../data/` | 歷來名單、對照表、執行 log 的留檔處 |

---

## 三個非直覺的前提

**沒搞懂這三點就會回報「已解鎖」但人其實還被擋著。**

### 1. DELETE 是識別項對稱的，不反查使用者

`user_risk_marks` 一筆識別項一列（`open_id` / 國碼+手機 / `base_email` 三選一）。
API 傳什麼型別就刪什麼型別的列，**不跨識別項連動**
（`gama-auth/internal/model/user_risk_mark.go` 的 `DeleteRiskMarksParams` 註解）。

→ 同一個人可能同時有 openID 標記和手機標記。**刪手機不會解掉 openID 標記。**

### 2. 解鎖名單給的是 openID，線上現存的標記卻是手機型別

客服給的欄位是 `gamapassID(解鎖)`。要先用歷史批次的對照表把 openID 換成手機。
同一個人在不同批次可能是**不同號碼**（換過手機），所以取**聯集**，不是取最新的那批。

### 3. `country_code` 是跟號碼分開加密的

`EncryptPhone` 把國碼和國內號碼各自加密（`internal/service/user_risk_mark.go:377`）。
`+1 975665292` 和 `+886 975665292` 的 `phone` 密文**完全一樣**，只有 `country_code` 不同，
而第一批名單裡真的有 `+1` 的號碼。查 SQL 一律成對比對，只 join `phone` 會撈到別人。

---

## 解鎖流程

### Step 1 — 產名單與落差報告

```bash
TAG=$(date +%F)   # 同一天有第二批就 2026-09-04b，別讓檔名互蓋
python3 ~/.claude/skills/risk-marks/prepare_unlock.py \
  --targets "/Users/meisonlee/Downloads/<客服給的解鎖名單>.csv" \
  --tag "$TAG" \
  2>&1 | tee ~/Gama/tools/script/api-risk-marks/data/prepare_unlock_$TAG.log
```

`--out-dir` 預設就是 `data/`，**不要改**——產出的名單本身就是留檔的一部分。

輸出兩份可以直接餵給 `delete_risk_marks.py` 的清單：
`data/unlock_phones_<tag>.csv`（手機聯集）和 `data/unlock_openids_<tag>.csv`
（去掉標題的 openID）。**openID 型別一律用後者，絕對不要把客服原始 CSV 當 `--file`**：
`read_subjects` 的 `HEADER_WORDS` 不認得 `gamapassID(解鎖)`，會把標題當成一筆 subject 送出去。

同時印出三件必須回報給使用者的事：

- **完全沒有手機對照的 openID** — 對他們刪手機是空操作。
- **只出現在某一批的手機** — 該批的手機標記若已被整批清掉，會回 not found（正常）。
- **同時在第一批 openID 標記清單裡的 openID** — 刪手機不會動到，附帶查證 SQL。

腳本用「第一欄是不是純數字」判斷標題列，所以 `gamapassID(解鎖)`
這種不在 `HEADER_WORDS` 裡的標題也能正確跳過。第二欄的公文備註不影響。

### Step 2 — 回報並等確認

**這是不可逆的線上操作。** 把 Step 1 的落差、要送的完整 payload（`--dry-run` 或直接列 JSON）、
以及環境（PROD？）攤給使用者，等明確同意再跑。openID 型別的標記要不要一起刪，
**一定要問**，不要自己決定。

### Step 3 — 執行並留檔

```bash
cd ~/Gama/tools/script/api-risk-marks
python3 delete_risk_marks.py \
  --file data/unlock_phones_$TAG.csv \
  --type phone \
  --base-url https://api.accounts.gamania.com/ \
  --client-id Yzk2MWRhMmEtOTEwNy00YmIzLTkwOTYtN2NjZGY2MDI3MTNl \
  --risk-type-id 1 \
  --reason "$TAG 客訴/申訴 解鎖 risk marks delete" \
  --operator meisonlee@gamania.com \
  2>&1 | tee data/delete_unlock_phones_$TAG.log
```

openID 型別是**另一次**執行：`--file data/unlock_openids_$TAG.csv --type openID`，
log 導到 `data/delete_unlock_openids_$TAG.log`。`--reason` 沿用同一句就好，
兩者本來就是不同型別的列，不必在 reason 裡再區分一次。

### Step 4 — 解讀結果

API 只回總數（`deleted` / not found），**不會說是哪幾筆沒中**。
`sent > deleted` 先對 Step 1 的「只出現在某一批的手機」——數字對得上就是預期內。

---

## PROD 參數

| 參數 | 值 |
|---|---|
| `--base-url` | `https://api.accounts.gamania.com/` |
| `--client-id` | `Yzk2MWRhMmEtOTEwNy00YmIzLTkwOTYtN2NjZGY2MDI3MTNl`（GTW） |
| `--risk-type-id` | `1`（線上唯一的 risk type，`GTW_MSTC_BLACK`） |
| `--operator` | 執行者本人公司信箱 |
| `--token` | 不用給，腳本內建的預設值可以直接打 |

dev 的參數在工具目錄的 `README.md`。每批上限 100 筆，`--sleep` 預設 10 秒
（手機／email 會在後端加密，較吃 CPU；openID 不會）。幾十筆的解鎖單通常一個 batch 就結束。

---

## 查證 SQL

openID 型別的標記（PROD proxy 見 `~/Gama/db.sh`，port 58505）：

```sql
SELECT id, risk_type_id, open_id, operation_reason, operator_email, created_time
FROM user_risk_marks WHERE open_id IN ('...', '...');
```

要一次看兩種型別，**join 必須成對比對國碼＋號碼**：

```sql
SELECT u.open_id, urm.id AS mark_id, urm.risk_type_id,
       CASE WHEN urm.open_id IS NOT NULL THEN 'openID' ELSE 'phone' END AS subject_type
FROM users u
JOIN user_risk_marks urm
  ON (urm.open_id = u.open_id)
  OR (urm.country_code = u.country_code AND urm.phone = u.phone)
WHERE u.open_id IN ('...', '...');
```

這個 join 只看得到 `users` 現存的那支號碼；使用者換過手機的話，舊號碼的標記列查不到但**仍然存在、仍然擋人**。

---

## 常見錯誤

| 錯誤 | 後果 |
|---|---|
| 只刪手機就回報「已解鎖」 | openID 標記還在，人照樣被擋 |
| 只用最新一批的對照表 | 換過手機的人漏刪舊號碼的標記 |
| SQL 只 join `phone` | 撈到不同國碼的別人 |
| 把 `gamapassID(解鎖)` 標題當成一筆資料送出 | 多送一筆垃圾 subject |
| 看到 `sent > deleted` 就當成失敗 | not found 是正常結果，不是錯誤 |
| 沒問就刪 openID 標記 | 超出使用者授權的範圍 |

---

## 歷史批次狀態（截至 2026-09-04）

| 批次 | 匯入的識別項 | 現況 |
|---|---|---|
| 第一批 GAMAPASS-3531 | openID（16973）＋手機 | **手機標記已於 2026-08-28 整批刪除；openID 標記仍在** |
| 第二批 GAMAPASS-3589 | 手機（44203） | 仍在。線上現存的手機標記都來自這批 |

第一批手機標記已被清掉的證據：第二批 import log 結尾是
`44203 sent, 44203 inserted, 0 duplicated`。兩批手機重疊很大，
若第一批的列還在，這裡會出現大量 `duplicated`。

**有新批次時**：把對照表放進 `data/`，在 `prepare_unlock.py` 的 `MAPPINGS`
加一列；若該批是用 openID 匯入的，同時加進 `OPENID_MARK_LISTS`。

---

## 加標注（import）

同一組參數，`delete_risk_marks.py` 換成 `import_risk_marks.py`、`--reason` 改成匯入的描述。
輸入是每行一筆的 CSV（手機必須含國碼、以 `+` 開頭）。回報 `inserted` / `duplicated`。
上萬筆時 `--sleep 10`，1 萬筆手機約 20 分鐘。
