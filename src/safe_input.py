#!/usr/bin/env python3
"""
安全なテキスト入力機能を提供するモジュール
"""
try:
    import gnureadline as readline
except:
    import readline
from datetime import datetime
from typing import Optional
from rich.console import Console
from simple_term_menu import TerminalMenu


class HistoryManager:
    """readline履歴の管理クラス"""
    def __init__(self):
        self.histories = {}
    
    def set_history(self, context):
        """指定されたコンテキストの履歴を設定"""
        try:
            # 現在の履歴を保存
            current_history = []
            for i in range(readline.get_current_history_length()):
                current_history.append(readline.get_history_item(i + 1))
            
            # 履歴をクリア
            readline.clear_history()
            
            # 指定されたコンテキストの履歴を復元
            if context in self.histories:
                for item in self.histories[context]:
                    readline.add_history(item)
            
            return current_history
        except:
            return []
    
    def save_history(self, context, history):
        """履歴を保存"""
        try:
            # 現在の履歴を取得
            current_history = []
            for i in range(readline.get_current_history_length()):
                current_history.append(readline.get_history_item(i + 1))
            
            # 保存
            self.histories[context] = current_history
        except:
            pass


# Escキーでのファイル名補完を無効化
readline.set_completer(None)

# グローバルな履歴管理インスタンス
history_manager = HistoryManager()



def safe_text_input(prompt, history: str, validator=None, handle_eof=True):
    """安全なテキスト入力"""
    # 指定された履歴コンテキストに切り替え
    saved_history = history_manager.set_history(history)
    
    try:
        while True:
            try:
                user_input = input(prompt)
            except EOFError:
                if handle_eof:
                    print()
                    return None  # Ctrl+Dの場合はNoneを返す
                else:
                    raise
            
            # バリデーション
            if user_input and validator and not validator(user_input):
                console = Console()
                console.print("[red]入力形式が正しくありません。再入力してください。[/red]")
                continue
            
            return user_input
    finally:
        # 指定された履歴コンテキストを保存
        history_manager.save_history(history, [])
        
        # 以前の履歴を復元
        readline.clear_history()
        for item in saved_history:
            readline.add_history(item)


def safe_text_input_with_user_completion(prompt, history: str, user_info, validator=None, handle_eof=True):
    """ユーザー名補完機能付きの安全なテキスト入力"""
    # 指定された履歴コンテキストに切り替え
    saved_history = history_manager.set_history(history)
    
    # 元の補完設定を保存
    saved_completer = readline.get_completer()
    saved_delims = readline.get_completer_delims()
    
    try:
        # ユーザー名補完を設定
        if user_info:
            readline.set_completer(user_info.user_completer)
            readline.set_completer_delims(' \t\n,')  # コンマ区切り対応
            
            # readline補完を有効化
            readline.parse_and_bind("tab: complete")
            
            # 補完機能の案内
            if len(user_info.user_list) > 0:
                console = Console()
                console.print(f"[dim]Tabキーでユーザー名補完を使用できます ({len(user_info.user_list)}件)[/dim]")
        
        while True:
            try:
                user_input = input(prompt)
            except EOFError:
                if handle_eof:
                    print()
                    return None  # Ctrl+Dの場合はNoneを返す
                else:
                    raise
            
            # バリデーション
            if user_input and validator and not validator(user_input):
                console = Console()
                console.print("[red]入力形式が正しくありません。再入力してください。[/red]")
                continue
            
            return user_input
    finally:
        # 補完設定を復元
        readline.set_completer(saved_completer)
        readline.set_completer_delims(saved_delims)
        
        # Tab補完を無効化（デフォルトの動作に戻す）
        readline.parse_and_bind("tab: self-insert")
        
        # 指定された履歴コンテキストを保存
        history_manager.save_history(history, [])
        
        # 以前の履歴を復元
        readline.clear_history()
        for item in saved_history:
            readline.add_history(item)


def safe_number_input(prompt, history: str, min_val=None, max_val=None, default=None):
    """安全な数値入力"""
    def number_validator(text):
        try:
            num = int(text)
            if min_val is not None and num < min_val:
                return False
            if max_val is not None and num > max_val:
                return False
            return True
        except ValueError:
            return False
    
    range_info = ""
    if min_val is not None and max_val is not None:
        range_info = f" ({min_val}-{max_val})"
    elif min_val is not None:
        range_info = f" ({min_val}以上)"
    elif max_val is not None:
        range_info = f" ({max_val}以下)"
    
    result = safe_text_input(
        f"{prompt}{range_info}",
        history=history,
        validator=number_validator
    )
    
    if result is None:
        return None  # Ctrl+D
    elif result == "":
        return ""  # 無入力
    else:
        return int(result)


def _parse_date(date_str: str) -> Optional[str]:
    """日付文字列をパースしてタイムスタンプ形式に変換"""
    if not date_str.strip():
        return None
        
    date_str = date_str.strip()
    
    try:
        # YYYYMMDD形式の場合
        if len(date_str) == 8 and date_str.isdigit():
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            dt = datetime(year, month, day)
            return dt.strftime('%Y-%m-%d 00:00:00')
        
        # Y-M-D形式の場合
        elif '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 3:
                year, month, day = map(int, parts)
                dt = datetime(year, month, day)
                return dt.strftime('%Y-%m-%d 00:00:00')
        
        return None
    except (ValueError, TypeError):
        return None


def safe_date_input(prompt: str, history: str) -> Optional[str]:
    """安全な日付入力"""
    console = Console()
    console.print("[dim]日付形式: YYYYMMDD または Y-M-D[/dim]")
    console.print("[dim]例: 20230101 または 2023-1-1[/dim]")
    
    def date_validator(text):
        return _parse_date(text) is not None
    
    date_input = safe_text_input(
        f"{prompt} (形式: YYYYMMDD または Y-M-D)",
        history=history,
        validator=date_validator
    )
    
    if date_input is None:
        return None  # Ctrl+D
    elif date_input == "":
        return ""  # 無入力
    else:
        return _parse_date(date_input)


def yes_no_menu(title, default_yes=True):
    """はい/いいえ選択メニュー"""
    options = ["はい", "いいえ"]
    default_index = 0 if default_yes else 1
    
    terminal_menu = TerminalMenu(
        options,
        title=title,
        cursor_index=default_index,
        show_search_hint=True
    )
    
    choice_index = terminal_menu.show()
    
    if choice_index is None:
        return None  # キャンセル
    
    return choice_index == 0  # はい=True, いいえ=False
