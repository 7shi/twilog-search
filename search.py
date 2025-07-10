#!/usr/bin/env python3
"""
Twilogデータベースに対するベクトル検索システム
"""
import argparse
import json
import asyncio
import websockets
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Generator, Optional
from llm7shi import bold
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from simple_term_menu import TerminalMenu
from safe_input import safe_text_input, safe_number_input, safe_date_input, yes_no_menu
from twilog_client import TwilogClient
from data_csv import TwilogDataAccess


class TwilogVectorSearch:
    """Twilogベクトル検索クラス"""
    
    def __init__(self, db_path: str, websocket_url: str = "ws://localhost:8765"):
        """
        初期化
        
        Args:
            db_path: データベースファイルのパス
            websocket_url: RuriサーバーのWebSocket URL
        """
        self.db_path = db_path
        self.websocket_url = websocket_url
        
        # データアクセス層の初期化
        self.data_access = TwilogDataAccess(db_path)
        
        # ユーザーフィルタリング設定
        self.user_filter = {}
        
        # 日付フィルタリング設定
        self.date_filter = {}
        
        # 表示件数設定
        self.top_k = 10
        
        # TwilogClientの初期化
        self.client = TwilogClient(websocket_url)
        
        # ユーザー情報の読み込み
        print("ユーザー情報を読み込み中...")
        self.post_user_map, self.user_post_counts = self.data_access.load_user_data()
        
        # WebSocketサーバー接続確認
        try:
            print("WebSocketサーバーへの接続を確認中...")
            asyncio.run(self._test_websocket_connection())
            print("WebSocketサーバー接続成功")
        except Exception as e:
            print(f"WebSocketサーバー接続失敗: {e}")
            print("WebSocketサーバーが利用できません。twilog_server.py start でデーモンを起動してください。")
            raise RuntimeError("WebSocketサーバーが必要です")
    
    
    async def _test_websocket_connection(self):
        """WebSocketサーバーへの接続テスト"""
        try:
            # TwilogClientのget_statusメソッドを使用してサーバータイプを確認
            result = await self.client.get_status()
        except Exception as e:
            raise RuntimeError(f"接続テスト失敗: {e}")
        
        if "error" in result:
            raise RuntimeError(f"サーバーエラー: {result['error']}")
        
        # サーバータイプがTwilogServerかどうか確認
        server_type = result.get('server_type', '')
        if server_type != 'TwilogServer':
            raise RuntimeError(f"期待されるサーバータイプ 'TwilogServer' ではありません: {server_type}")
    
    def _search_remote(self, query: str) -> list:
        """リモートで検索を実行する"""
        try:
            return asyncio.run(self.client.search_similar(query, None))
        except Exception as e:
            raise RuntimeError(f"リモート検索に失敗: {e}")
    
    def _is_user_allowed(self, user: str) -> bool:
        """ユーザーがフィルタリング条件を満たすかチェック"""
        if not self.user_filter:
            return True
        
        # includes/excludesのチェック（排他的）
        if "includes" in self.user_filter:
            if user not in self.user_filter["includes"]:
                return False
        elif "excludes" in self.user_filter:
            if user in self.user_filter["excludes"]:
                return False
        
        # threshold系のチェック（組み合わせ可能）
        post_count = self.user_post_counts.get(user, 0)
        
        if "threshold_min" in self.user_filter:
            if post_count < self.user_filter["threshold_min"]:
                return False
                
        if "threshold_max" in self.user_filter:
            if post_count > self.user_filter["threshold_max"]:
                return False
        
        return True
    
    def _parse_date(self, date_str: str) -> Optional[str]:
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
    
    def _is_date_allowed(self, timestamp: str) -> bool:
        """投稿日時がフィルタリング条件を満たすかチェック"""
        if not self.date_filter:
            return True
            
        if not timestamp:
            return True
            
        try:
            post_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            
            if "from" in self.date_filter and "to" not in self.date_filter:
                # from のみ指定
                from_dt = datetime.strptime(self.date_filter["from"], '%Y-%m-%d %H:%M:%S')
                return post_dt >= from_dt
                
            elif "to" in self.date_filter and "from" not in self.date_filter:
                # to のみ指定
                to_dt = datetime.strptime(self.date_filter["to"], '%Y-%m-%d %H:%M:%S')
                return post_dt <= to_dt
                
            elif "from" in self.date_filter and "to" in self.date_filter:
                # from-to 両方指定
                from_dt = datetime.strptime(self.date_filter["from"], '%Y-%m-%d %H:%M:%S')
                to_dt = datetime.strptime(self.date_filter["to"], '%Y-%m-%d %H:%M:%S')
                return from_dt <= post_dt <= to_dt
                
        except (ValueError, TypeError):
            return True
            
        return True
    
    
    def _user_filter_menu(self):
        """ユーザーフィルタリングメニュー"""
        while True:
            print(f"\n=== ユーザーフィルタリング設定 ===")
            print(f"現在の設定: {self._format_filter_status()}")
            
            options = [
                "[1] none（すべてのユーザー）",
                "[2] includes（指定ユーザーのみ）",
                "[3] excludes（指定ユーザーを除外）",
                "[4] threshold min（投稿数下限）",
                "[5] threshold max（投稿数上限）"
            ]
            
            terminal_menu = TerminalMenu(
                options,
                title="フィルター方式を選択してください (数字キー: 直接選択, ↑↓: 移動, Enter: 決定, Esc: 戻る):",
                show_search_hint=True
            )
            
            choice_index = terminal_menu.show()
            
            if choice_index is None:
                return
            
            if choice_index == 0:  # none
                self.user_filter = {}
                print("フィルタリングを無効にしました")
                return  # noneは即座に抜ける
                
            elif choice_index == 1:  # includes
                users_input = safe_text_input(
                    "ユーザー名をコンマ区切りで入力: ",
                    history="user"
                )
                
                if users_input is None:
                    # Ctrl+Dの場合、何も変更せずにメニューに戻る
                    continue
                elif users_input.strip():
                    users = [user.strip() for user in users_input.split(',') if user.strip()]
                    # includes設定時は他の設定をすべてクリア
                    self.user_filter = {"includes": users}
                    console = Console()
                    console.print(f"[green]includes設定: {len(users)}人のユーザーを対象[/green]")
                    return  # includesは即座に抜ける
                else:
                    # 無入力の場合、値を消去するか確認
                    current_value = self.user_filter.get("includes", None)
                    if current_value is not None:
                        should_clear = yes_no_menu(
                            f"現在のincludes設定({len(current_value)}人)を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            console = Console()
                            del self.user_filter["includes"]
                            console.print(f"[green]includes設定を消去しました[/green]")
                            console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                    # 回答に関わらずメニューに戻る
                    continue
                    
            elif choice_index == 2:  # excludes
                users_input = safe_text_input(
                    "除外ユーザー名をコンマ区切りで入力: ",
                    history="user"
                )
                
                if users_input is None:
                    # Ctrl+Dの場合、何も変更せずにメニューに戻る
                    continue
                elif users_input.strip():
                    users = [user.strip() for user in users_input.split(',') if user.strip()]
                    # excludes設定時は他の設定をすべてクリア
                    self.user_filter = {"excludes": users}
                    console = Console()
                    console.print(f"[green]excludes設定: {len(users)}人のユーザーを除外[/green]")
                    return  # excludesは即座に抜ける
                else:
                    # 無入力の場合、値を消去するか確認
                    current_value = self.user_filter.get("excludes", None)
                    if current_value is not None:
                        should_clear = yes_no_menu(
                            f"現在のexcludes設定({len(current_value)}人)を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            console = Console()
                            del self.user_filter["excludes"]
                            console.print(f"[green]excludes設定を消去しました[/green]")
                            console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                    # 回答に関わらずメニューに戻る
                    continue
                    
            elif choice_index == 3:  # threshold min
                min_posts = safe_number_input(
                    "投稿数下限を入力: ",
                    history="threshold",
                    min_val=1
                )
                
                if min_posts is None:
                    # Ctrl+Dの場合、何も変更せずにメニューに戻る
                    continue
                elif min_posts == "":
                    # 無入力の場合、値を消去するか確認
                    current_value = self.user_filter.get("threshold_min", None)
                    if current_value is not None:
                        should_clear = yes_no_menu(
                            f"現在のthreshold min設定({current_value})を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            console = Console()
                            del self.user_filter["threshold_min"]
                            console.print(f"[green]threshold min設定を消去しました[/green]")
                            console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                    # 回答に関わらずメニューに戻る
                    continue
                
                # 上限との整合性チェック
                console = Console()
                if "threshold_max" in self.user_filter:
                    max_posts = self.user_filter["threshold_max"]
                    if min_posts >= max_posts:
                        console.print(f"[yellow]threshold max設定({max_posts})がthreshold min設定({min_posts})と矛盾するため削除しました[/yellow]")
                
                # includes/excludesを削除し、threshold系のみ保持
                new_filter = {"threshold_min": min_posts}
                if "threshold_max" in self.user_filter:
                    max_posts = self.user_filter["threshold_max"]
                    if min_posts < max_posts:
                        new_filter["threshold_max"] = max_posts
                self.user_filter = new_filter
                    
                console.print(f"[green]threshold min={min_posts}: 投稿数{min_posts}以上のユーザーを対象[/green]")
                console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                # threshold minはメニューに戻る（continueで次のループへ）
                    
            elif choice_index == 4:  # threshold max
                # 下限が設定されている場合は、それより大きい値を要求
                min_threshold = None
                if "threshold_min" in self.user_filter:
                    min_threshold = self.user_filter["threshold_min"] + 1
                
                max_posts = safe_number_input(
                    "投稿数上限を入力: ",
                    history="threshold",
                    min_val=min_threshold or 1
                )
                
                if max_posts is None:
                    # Ctrl+Dの場合、何も変更せずにメニューに戻る
                    continue
                elif max_posts == "":
                    # 無入力の場合、値を消去するか確認
                    current_value = self.user_filter.get("threshold_max", None)
                    if current_value is not None:
                        should_clear = yes_no_menu(
                            f"現在のthreshold max設定({current_value})を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            console = Console()
                            del self.user_filter["threshold_max"]
                            console.print(f"[green]threshold max設定を消去しました[/green]")
                            console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                    # 回答に関わらずメニューに戻る
                    continue
                
                # 下限との整合性チェック
                console = Console()
                if "threshold_min" in self.user_filter:
                    min_posts = self.user_filter["threshold_min"]
                    if max_posts <= min_posts:
                        console.print(f"[yellow]threshold min設定({min_posts})がthreshold max設定({max_posts})と矛盾するため削除しました[/yellow]")
                
                # includes/excludesを削除し、threshold系のみ保持
                new_filter = {"threshold_max": max_posts}
                if "threshold_min" in self.user_filter:
                    min_posts = self.user_filter["threshold_min"]
                    if min_posts < max_posts:
                        new_filter["threshold_min"] = min_posts
                self.user_filter = new_filter
                    
                console.print(f"[green]threshold max={max_posts}: 投稿数{max_posts}以下のユーザーを対象[/green]")
                console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
                # threshold maxはメニューに戻る（continueで次のループへ）
    
    def _format_filter_status(self) -> str:
        """フィルタリング状態を文字列でフォーマット"""
        if not self.user_filter:
            return "すべてのユーザー"
        
        status_parts = []
        
        # includes/excludesは排他的
        if "includes" in self.user_filter:
            status_parts.append(f"includes ({len(self.user_filter['includes'])}人)")
        elif "excludes" in self.user_filter:
            status_parts.append(f"excludes ({len(self.user_filter['excludes'])}人)")
        
        # threshold系は組み合わせ可能
        if "threshold_min" in self.user_filter:
            status_parts.append(f"min={self.user_filter['threshold_min']}")
        if "threshold_max" in self.user_filter:
            status_parts.append(f"max={self.user_filter['threshold_max']}")
        
        return " + ".join(status_parts) if status_parts else "unknown"
    
    def _top_k_menu(self):
        """表示件数設定メニュー"""
        console = Console()
        console.print(f"\n[bold]=== 表示件数設定 ===[/bold]")
        console.print(f"現在の設定: {self.top_k}件")
        
        new_top_k = safe_number_input(
            "表示件数を入力: ",
            history="top_k",
            min_val=1,
            max_val=100,
            default=self.top_k
        )
        
        if new_top_k is not None:
            self.top_k = new_top_k
            console.print(f"[green]表示件数を{new_top_k}件に設定しました[/green]")
    
    def _date_filter_menu(self):
        """日付フィルタリングメニュー"""
        print(f"\n=== 日付フィルタリング設定 ===")
        
        while True:
            print(f"現在の設定: {self._format_date_filter_status()}")
            options = [
                "[1] all（すべての日付）",
                "[2] from（開始日時を設定）",
                "[3] to（終了日時を設定）"
            ]
            terminal_menu = TerminalMenu(
                options,
                title="日付フィルター方式を選択してください (数字キー: 直接選択, ↑↓: 移動, Enter: 決定, Esc: 戻る):",
                show_search_hint=True
            )
            choice_index = terminal_menu.show()
            
            if choice_index is None:
                return
            
            if choice_index == 0:  # all
                self.date_filter = {}
                print("日付フィルタリングを無効にしました")
                return  # allは即座に抜ける
                
            elif choice_index == 1:  # from
                # 日付入力処理をインライン展開
                from_date = safe_date_input("開始日時を入力: ", "date_input")
                
                if from_date is None:
                    continue  # Ctrl+Dの場合はメニューに戻る
                elif from_date == "":
                    # 無入力の場合、値を消去するか確認
                    if "from" in self.date_filter:
                        current_value = self.date_filter["from"][:10]
                        should_clear = yes_no_menu(
                            f"現在のfrom設定({current_value})を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            del self.date_filter["from"]
                            console.print(f"[green]from設定を消去しました[/green]")
                else:
                    # 適切な日付が入力された場合の処理
                    console = Console()
                    # toは引き継ぐが、他の設定はクリア
                    new_filter = {"from": from_date}
                    if "to" in self.date_filter:
                        to_date = self.date_filter["to"]
                        if from_date < to_date:
                            new_filter["to"] = to_date
                        else:
                            console.print(f"[yellow]to設定({to_date[:10]})がfrom設定({from_date[:10]})と矛盾するため削除しました[/yellow]")
                    self.date_filter = new_filter
                    console.print(f"[green]from設定: {from_date}以降の投稿を対象[/green]")
                # from設定後はメニューに戻る
                    
            elif choice_index == 2:  # to
                # 日付入力処理をインライン展開
                to_date = safe_date_input("終了日時を入力: ", "date_input")
                
                if to_date is None:
                    continue  # Ctrl+Dの場合はメニューに戻る
                elif to_date == "":
                    # 無入力の場合、値を消去するか確認
                    if "to" in self.date_filter:
                        current_value = self.date_filter["to"][:10]
                        should_clear = yes_no_menu(
                            f"現在のto設定({current_value})を消去しますか？",
                            default_yes=False
                        )
                        if should_clear:
                            del self.date_filter["to"]
                            console.print(f"[green]to設定を消去しました[/green]")
                else:
                    # 適切な日付が入力された場合の処理
                    console = Console()
                    # fromは引き継ぐが、他の設定はクリア
                    new_filter = {"to": to_date}
                    if "from" in self.date_filter:
                        from_date = self.date_filter["from"]
                        if from_date < to_date:
                            new_filter["from"] = from_date
                        else:
                            console.print(f"[yellow]from設定({from_date[:10]})がto設定({to_date[:10]})と矛盾するため削除しました[/yellow]")
                    self.date_filter = new_filter
                    console.print(f"[green]to設定: {to_date}以前の投稿を対象[/green]")
                # to設定後はメニューに戻る
    
    def _format_date_filter_status(self) -> str:
        """日付フィルタリング状態を文字列でフォーマット"""
        if not self.date_filter:
            return "すべての日付"
        elif "from" in self.date_filter and "to" not in self.date_filter:
            return f"from {self.date_filter['from']}"
        elif "to" in self.date_filter and "from" not in self.date_filter:
            return f"to {self.date_filter['to']}"
        elif "from" in self.date_filter and "to" in self.date_filter:
            return f"from {self.date_filter['from']} to {self.date_filter['to']}"
        return "unknown"
    
    def _show_help(self):
        """ヘルプメッセージを表示"""
        print("\n=== ヘルプ ===")
        print("特殊コマンド:")
        print("  /help, /?  - このヘルプを表示")
        print("  /user  - ユーザーフィルタリング設定")
        print("  /date  - 日付フィルタリング設定")
        print("  /top   - 表示件数設定")
        print("  /exit, /quit, /q  - プログラム終了")
        print("\n検索:")
        print("  検索クエリを入力すると意味的検索を実行")
        print("  例: プログラミング, git, 機械学習")
        print("\n終了:")
        print("  /exit, /quit, /q で終了")
    
    def search(self, query: str) -> Generator[Tuple[int, float, dict], None, None]:
        """
        リモート検索を実行する
        
        Args:
            query: 検索クエリ
            
        Yields:
            (rank, similarity, post_info)のタプル
        """
        # リモート検索を実行
        search_results = self._search_remote(query)
        
        if not search_results:
            return
        
        # 重複除去用の辞書
        seen_combinations = {}  # (user, content) -> (post_id, similarity, timestamp, url)
        
        rank = 1
        for post_id, similarity in search_results["data"]:
            user = self.post_user_map.get(post_id, '')
            
            # ユーザーフィルタリング条件をチェック
            if not self._is_user_allowed(user):
                continue
            
            # 投稿内容を個別取得
            post_info = self.data_access.get_post_content([post_id]).get(post_id, {})
            content = post_info.get('content', '').strip()
            timestamp = post_info.get('timestamp', '')
            url = post_info.get('url', '')
            
            # 日付フィルタリング条件をチェック
            if not self._is_date_allowed(timestamp):
                continue
            
            key = (user, content)
            
            # 重複チェック
            if key in seen_combinations:
                # 既存の投稿と同じユーザー・内容の場合、日付が古い方を優先
                existing_post_id, existing_similarity, existing_timestamp, existing_url = seen_combinations[key]
                if timestamp < existing_timestamp:
                    # 現在の投稿の方が古い場合、既存を置き換え
                    seen_combinations[key] = (post_id, similarity, timestamp, url)
                continue
            
            # 新しい組み合わせの場合、追加
            seen_combinations[key] = (post_id, similarity, timestamp, url)
            
            yield rank, similarity, {
                'post_id': post_id,
                'content': content,
                'timestamp': timestamp,
                'url': url,
                'user': user
            }
            
            rank += 1


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Twilogリモート検索システム")
    parser.add_argument("csv_file", nargs="?", default="twilog.csv", help="CSVファイルのパス（デフォルト: twilog.csv）")
    
    args = parser.parse_args()
    
    # 検索システムの初期化
    search_system = TwilogVectorSearch(args.csv_file)
    
    print(f"リモート検索システム準備完了")
    print("検索クエリを入力してください")
    print("特殊コマンド: /help でヘルプ表示")
    
    # 対話的な検索ループ
    while True:
        print()
        try:
            query = safe_text_input("> ", "main", handle_eof=False)
            if not query:
                continue
            query = query.strip()
        except EOFError:
            # Ctrl+Dの場合は終了
            print()
            break
        
        # 特殊コマンドの処理
        if query.startswith("/"):
            command = query[1:]
            if command in ["help", "?"]:
                search_system._show_help()
                continue
            elif command == "user":
                search_system._user_filter_menu()
                continue
            elif command == "date":
                search_system._date_filter_menu()
                continue
            elif command == "top":
                search_system._top_k_menu()
                continue
            elif command in ["exit", "quit", "q"]:
                print("プログラムを終了します")
                return
            else:
                print(f"エラー: 不明なコマンド '{command}'")
                search_system._show_help()
                continue
        
        # 検索実行
        results = []
        for result in search_system.search(query):
            results.append(result)
            if len(results) >= search_system.top_k:
                break
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 結果表示
        console = Console()
        rank_width = len(str(search_system.top_k))
        
        for rank, similarity, post_info in results:
            user = post_info['user'] or 'unknown'
            
            # ヘッダー情報（色付き）
            header = f"[bold cyan]{rank:{rank_width}d}[/bold cyan]: [bold green]{similarity:.5f}[/bold green] [bold blue]{user}[/bold blue] [yellow][{post_info['timestamp']}][/yellow]"
            
            # URLがある場合は追加
            if post_info.get('url'):
                header += f" [dim]{post_info['url']}[/dim]"
            
            # パネル表示
            panel = Panel(
                post_info['content'].rstrip(),
                title=header,
                title_align="left",
                border_style="bright_blue",
                padding=(0, 1)
            )
            
            console.print()  # パネル間のスペース
            console.print(panel)
        
        # 検索結果終了のセパレーター
        console.print()
        console.print(Rule(f"検索結果: {len(results)}件 (クエリ: '{query}')", style="dim"))


if __name__ == "__main__":
    main()
