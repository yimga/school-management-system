// Prevents additional console window on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use runmycampus_companion_tauri_lib::{
    rmc_fetch_maa, rmc_ingest_csv, rmc_login, rmc_sign_maa,
};

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            rmc_login,
            rmc_fetch_maa,
            rmc_sign_maa,
            rmc_ingest_csv,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
