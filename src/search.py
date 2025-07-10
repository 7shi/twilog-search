#!/usr/bin/env python3
"""
Twilogデータベースに対するベクトル検索システム
"""
import argparse
import asyncio
from typing import Tuple, Generator
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from settings import UserFilterSettings, DateFilterSettings, TopKSettings
from settings_ui import show_user_filter_menu, show_date_filter_menu, show_top_k_menu
from twilog_client import TwilogClient
from data_csv import TwilogDataAccess
from safe_input import safe_text_input


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
        self.user_filter_settings = UserFilterSettings({})
        
        # 日付フィルタリング設定
        self.date_filter_settings = DateFilterSettings()
        
        # 表示件数設定
        self.top_k_settings = TopKSettings(10)
        
        # TwilogClientの初期化
        self.client = TwilogClient(websocket_url)
        
        # ユーザー情報の読み込み
        print("ユーザー情報を読み込み中...")
        self.post_user_map, self.user_post_counts = self.data_access.load_user_data()
        
        # 設定クラスにユーザー情報を設定
        self.user_filter_settings = UserFilterSettings(self.user_post_counts)
        
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
        search_results = asyncio.run(self.client.search_similar(query, None))
        
        if not search_results:
            return
        
        # 重複除去用の辞書
        seen_combinations = {}  # (user, content) -> (post_id, similarity, timestamp, url)
        
        rank = 1
        for post_id, similarity in search_results["data"]:
            user = self.post_user_map.get(post_id, '')
            
            # ユーザーフィルタリング条件をチェック
            if not self.user_filter_settings.is_user_allowed(user):
                continue
            
            # 投稿内容を個別取得
            post_info = self.data_access.get_post_content([post_id]).get(post_id, {})
            content = post_info.get('content', '').strip()
            timestamp = post_info.get('timestamp', '')
            url = post_info.get('url', '')
            
            # 日付フィルタリング条件をチェック
            if not self.date_filter_settings.is_date_allowed(timestamp):
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
                show_user_filter_menu(search_system.user_filter_settings)
                continue
            elif command == "date":
                show_date_filter_menu(search_system.date_filter_settings)
                continue
            elif command == "top":
                show_top_k_menu(search_system.top_k_settings)
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
            if len(results) >= search_system.top_k_settings.get_top_k():
                break
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 結果表示
        console = Console()
        rank_width = len(str(search_system.top_k_settings.get_top_k()))
        
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
