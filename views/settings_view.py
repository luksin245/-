import streamlit as st

from services import backup_service
from utils.validators import ValidationError

st.title("⚙️ 설정")

if msg := st.session_state.pop("settings_msg", None):
    st.success(msg)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


st.subheader("DB 정보")
db_info = backup_service.get_db_info()
st.write("**DB 파일 경로**")
st.code(db_info["db_path"], language=None)
st.write("**백업 폴더 경로**")
st.code(db_info["backup_dir"], language=None)
st.write(
    f"**최근 백업 시각**: {db_info['last_backup_time'] if db_info['last_backup_time'] else '백업 기록 없음'}"
)

st.divider()

st.subheader("백업 생성")
st.caption("현재 데이터를 통째로 복사해 백업 폴더에 저장합니다. SQLite의 온라인 백업 기능을 사용하므로 프로그램을 쓰는 중에도 안전합니다.")

if st.button("💾 백업하기", type="primary"):
    result = backup_service.create_backup()
    st.session_state["settings_msg"] = (
        f"백업 성공: {result['filename']} "
        f"({_format_size(result['size_bytes'])}, {result['created_at']})"
    )
    st.rerun()

st.divider()

st.subheader("백업 목록 / 복구")

backups = backup_service.list_backups()

if not backups:
    st.info("아직 생성된 백업이 없습니다.")
else:
    st.dataframe(
        [
            {
                "파일명": b["filename"],
                "생성 시각": b["created_at"],
                "크기": _format_size(b["size_bytes"]),
            }
            for b in backups
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.session_state.setdefault("restore_select_suffix", 0)
    if st.session_state.pop("restore_clear_selection", False):
        st.session_state["restore_select_suffix"] += 1

    def _fmt_backup_option(i: int | None) -> str:
        if i is None:
            return "(선택 안함)"
        b = backups[i]
        return f"{b['filename']} ({b['created_at']}, {_format_size(b['size_bytes'])})"

    selected_idx = st.selectbox(
        "복구할 백업 선택",
        options=list(range(len(backups))),
        format_func=_fmt_backup_option,
        index=None,
        placeholder="(선택 안함)",
        key=f"restore_selected_idx_{st.session_state['restore_select_suffix']}",
    )
    selected_backup = backups[selected_idx] if selected_idx is not None else None

    @st.dialog("백업 복구")
    def open_restore_dialog(backup: dict) -> None:
        st.warning(
            f"선택한 백업 시점({backup['created_at']})으로 데이터를 복구합니다.\n\n"
            "현재 데이터는 복구 직전에 자동으로 안전 백업된 후 교체됩니다."
        )
        st.caption(f"복구 대상: {backup['filename']}")
        col_confirm, col_cancel = st.columns(2)
        with col_confirm:
            if st.button("복구", type="primary", key="confirm_restore", use_container_width=True):
                try:
                    result = backup_service.restore_backup(backup["filename"])
                    st.session_state["settings_msg"] = (
                        f"'{result['restored_from']}'(으)로 복구했습니다. "
                        f"복구 전 데이터는 '{result['pre_restore_backup']}'(으)로 안전하게 백업되었습니다."
                    )
                    st.session_state["restore_clear_selection"] = True
                    st.rerun()
                except ValidationError as e:
                    st.error(str(e))
        with col_cancel:
            if st.button("취소", key="cancel_restore", use_container_width=True):
                st.rerun()

    if st.button("♻️ 선택한 백업으로 복구", disabled=selected_backup is None):
        open_restore_dialog(selected_backup)
