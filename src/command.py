#!/usr/bin/env python3
"""
コマンドシステム - 検索アプリケーションのコマンド処理
"""
from functools import wraps
from typing import Dict, List, Callable, Optional
from rich.console import Console
from safe_input import completion_manager


class CommandHandler:
    """コマンド処理を行うクラス"""
    
    def __init__(self):
        self.should_exit = False
        self.command_registry: Dict[str, Dict] = {}
    
    def command(self, aliases: List[str], description: str):
        """コマンド登録デコレーター"""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            
            # すべてのエイリアスに対してコマンドを登録
            for alias in aliases:
                self.command_registry[alias] = {
                    'func': wrapper,
                    'description': description,
                    'aliases': aliases
                }
            
            return wrapper
        return decorator
    
    def execute(self, query: str) -> bool:
        """コマンドを実行。処理されればTrue、通常検索ならFalse"""
        if not query.startswith("/"):
            return False
        
        command_name = query[1:]  # "/" を除去
        
        if command_name in self.command_registry:
            try:
                self.command_registry[command_name]['func'](self)
            except Exception as e:
                console = Console()
                console.print(f"[red]コマンドエラー: {e}[/red]")
            return True
        else:
            console = Console()
            console.print(f"[red]エラー: 不明なコマンド '{command_name}'[/red]")
            self.show_help()
            return True
    
    def show_help(self):
        """利用可能なコマンドのヘルプを表示"""
        console = Console()
        console.print("\n=== 利用可能なコマンド ===")
        
        # コマンドを重複除去して登録順で表示
        seen_commands = set()
        
        for cmd_name, cmd_info in self.command_registry.items():
            if cmd_name not in seen_commands:
                aliases = cmd_info['aliases']
                description = cmd_info['description']
                aliases_str = ', '.join(f"/{alias}" for alias in aliases)
                console.print(f"  {aliases_str:<20} - {description}")
                seen_commands.update(aliases)
        
        console.print("\n検索:")
        console.print("  検索クエリを入力すると意味的検索を実行")
        console.print("  例: プログラミング, git, 機械学習")
    
    def get_command_completer(self):
        """コマンド補完用の関数を返す"""
        def command_completer(text: str, state: int):
            # "/" で始まる場合のみ補完
            if not text.startswith("/"):
                return None
            
            # "/" を除去してコマンド名を取得
            command_prefix = text[1:]
            
            # マッチするコマンドを検索
            matches = []
            for cmd_name in self.command_registry.keys():
                if cmd_name.startswith(command_prefix):
                    matches.append(f"/{cmd_name}")
            
            # 重複を除去してソート
            matches = sorted(list(set(matches)))
            
            if state < len(matches):
                return matches[state]
            return None
        
        return command_completer
    
    def setup_completion(self):
        """コマンド補完を設定したコンテキストマネージャーを返す"""
        return completion_manager.setup_completion(
            self.get_command_completer(),
            ' \t\n'
        )
