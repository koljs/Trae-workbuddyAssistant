//! WorkBuddy 应用内自动签到调度器。
//!
//! 软件运行期间每 30 秒检查一次：开关开启、本地时间到达设定时刻且当天
//! 尚未执行过自动签到时，对「今日未签且未标记需重登」的账号发起一键签到，
//! 复用手动签到的全部链路（token 刷新、状态查询、日志、全局轮次锁）。
//! 应用未运行的时段不会补签；如需覆盖关机时段，请使用计划任务方案
//! （当前计划任务仅支持 Trae 账号）。
//!
//! 与手动签到的并发关系：共享 `checkin_all_with` 的全局轮次锁，任一时刻
//! 只允许一轮签到。若自动触发时手动签到正在执行，本轮放弃并在下个周期
//! 重试（不写入当日完成标记）。

use chrono::Timelike;
use serde_json::{json, Value};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

use super::checkin::{checkin_all_with, checked_in_today};
use super::refresh::load_accounts;

/// 检查间隔（秒）。取 30 秒：到点误差最多半分钟，扫描开销可忽略。
const TICK_SECS: u64 = 30;

/// 状态文件：记录最近一次自动签到的日期与结果，防止同一天重复触发。
const STATE_FILE: &str = "workbuddy_auto_checkin.json";

/// 轮次锁被拒时的错误文案（与 checkin.rs 中的 RoundGuard 返回一致）。
const ROUND_BUSY_ERROR: &str = "已有一轮签到正在进行，请稍后再试";

fn state_path() -> std::path::PathBuf {
    super::store_path().join(STATE_FILE)
}

fn read_state() -> Value {
    crate::fs_utils::read_json(&state_path())
}

fn write_state(entry: &Value) {
    let _ = crate::fs_utils::write_json(&state_path(), entry);
}

/// "HH:MM" -> 当天分钟数；非法格式返回 None。
fn parse_hhmm(text: &str) -> Option<u32> {
    let mut parts = text.trim().splitn(2, ':');
    let h: u32 = parts.next()?.trim().parse().ok()?;
    let m: u32 = parts.next()?.trim().parse().ok()?;
    (h < 24 && m < 60).then_some(h * 60 + m)
}

/// 今日是否已执行过自动签到（含「无账号/全部已签」的跳过标记）。
fn already_ran_today(today: &str) -> bool {
    read_state()
        .get("lastRunDate")
        .and_then(Value::as_str)
        .is_some_and(|d| d == today)
}

/// 启动调度线程（随应用生命周期常驻，无需显式停止）。
pub fn spawn_scheduler(app: AppHandle) {
    let result = std::thread::Builder::new()
        .name("wb-auto-checkin".to_string())
        .spawn(move || loop {
            tick(&app);
            std::thread::sleep(Duration::from_secs(TICK_SECS));
        });
    if let Err(e) = result {
        eprintln!("WorkBuddy 自动签到调度线程启动失败: {e}");
    }
}

/// 单次检查：到达触发条件则执行一轮自动签到。
fn tick(app: &AppHandle) {
    let Some(state) = app.try_state::<crate::state::AppState>() else {
        return;
    };
    let settings = state.settings();
    if !settings.wb_auto_checkin {
        return;
    }
    let Some(target) = parse_hhmm(&settings.wb_auto_checkin_time) else {
        return; // 时间配置非法：跳过本周期
    };

    let now = chrono::Local::now();
    let today = now.date_naive().to_string();
    if now.hour() * 60 + now.minute() < target {
        return;
    }
    if already_ran_today(&today) {
        return;
    }

    // 挑选目标账号：今日未签且未标记需重登（需重登账号每天必失败，徒增噪音）
    let accounts = load_accounts();
    let ids: Vec<String> = accounts
        .iter()
        .filter(|a| !checked_in_today(a))
        .filter(|a| a.get("needs_relogin").and_then(Value::as_bool) != Some(true))
        .filter_map(|a| a.get("id").and_then(Value::as_str).map(str::to_string))
        .collect();

    // 没有账号 / 全部已签或需重登：本周期直接跳过，不写当日完成标记，
    // 用户当天稍后新增的账号仍可被自动签到（本地文件扫描，开销可忽略）
    if accounts.is_empty() || ids.is_empty() {
        return;
    }

    // 执行签到（与手动签到共享全局轮次锁，互斥）
    let results = checkin_all_with(Some(&ids), |index, total, entry| {
        let _ = app.emit(
            "workbuddy-checkin-progress",
            json!({
                "index": index,
                "total": total,
                "accountId": entry.get("accountId"),
                "email": entry.get("email"),
                "result": entry.get("result"),
                "error": entry.get("error"),
            }),
        );
    });

    // 手动签到正在进行被轮次锁拒绝：不标记今天完成，下个周期重试
    if results.len() == 1
        && results[0].get("error").and_then(Value::as_str) == Some(ROUND_BUSY_ERROR)
    {
        return;
    }

    let ok = results.iter().filter(|r| r["result"] == "success").count();
    let already = results.iter().filter(|r| r["result"] == "already").count();
    let failed = results.len() - ok - already;
    write_state(&json!({
        "lastRunDate": today,
        "ts": super::now_ms(),
        "ok": ok,
        "already": already,
        "failed": failed,
        "total": results.len(),
    }));
    // source=auto：前端据此区分自动/手动签到，各自负责通知，避免重复 toast
    let _ = app.emit(
        "workbuddy-checkin-done",
        json!({
            "ok": ok,
            "already": already,
            "failed": failed,
            "total": results.len(),
            "source": "auto",
        }),
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_valid_hhmm() {
        assert_eq!(parse_hhmm("09:00"), Some(9 * 60));
        assert_eq!(parse_hhmm("23:59"), Some(23 * 60 + 59));
        assert_eq!(parse_hhmm(" 00:00 "), Some(0));
    }

    #[test]
    fn rejects_invalid_hhmm() {
        assert_eq!(parse_hhmm("24:00"), None);
        assert_eq!(parse_hhmm("09:60"), None);
        assert_eq!(parse_hhmm(""), None);
        assert_eq!(parse_hhmm("9点"), None);
        assert_eq!(parse_hhmm("0900"), None);
    }
}
