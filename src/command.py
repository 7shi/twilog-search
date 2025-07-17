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
        
        # コマンドと引数を分離（最初のスペースで分割）
        command_part = query[1:]  # "/" を除去
        if not command_part:
            return False
        
        # 最初のスペースで分割
        if ' ' in command_part:
            command_name, args_str = command_part.split(' ', 1)
        else:
            command_name = command_part
            args_str = ""
        
        if command_name in self.command_registry:
            try:
                func = self.command_registry[command_name]['func']
                # 引数を想定するハンドラには引数文字列を渡す
                import inspect
                sig = inspect.signature(func)
                if len(sig.parameters) > 1:  # handler以外のパラメータがある場合
                    args = [self, args_str]
                else:
                    args = [self]
                func(*args)
            except Exception as e:
                console = Console()
                console.print(f"[red]コマンドエラー: {e}[/red]")
            return True
        else:
            console = Console()
            console.print(f"[red]エラー: 不明なコマンド '{command_name}'[/red]")
            self.show_help()
            return True
    
    def parse_range_specification(self, spec: str) -> List[int]:
        """
        範囲指定文字列を解析してランク番号のリストを返す
        
        Args:
            spec: 範囲指定文字列 (例: "1,5", "23-50", "1-3,7,10-15")
        
        Returns:
            list: ランク番号のリスト（1ベース）
        """
        if not spec or not spec.strip():
            return []
        
        ranks = []
        parts = spec.split(',')
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
                
            if '-' in part:
                # 範囲指定（例：23-50）
                try:
                    start, end = part.split('-', 1)
                    start = int(start.strip())
                    end = int(end.strip())
                    if start <= end:
                        ranks.extend(range(start, end + 1))
                except ValueError:
                    continue
            else:
                # 個別指定（例：5）
                try:
                    rank = int(part)
                    ranks.append(rank)
                except ValueError:
                    continue
        
        # 重複を削除してソート
        return sorted(list(set(ranks)))
    
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
