#!/usr/bin/env python3
"""
Twilogデータベースに対するベクトル検索システム
"""
import sys
import argparse
import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from settings_ui import show_user_filter_menu, show_date_filter_menu, show_top_k_menu
from twilog_client import TwilogClient
from safe_input import safe_text_input
from search_engine import SearchEngine

async def test_websocket_connection(client):
    """WebSocketサーバーへの接続テスト"""
    # TwilogClientのget_statusメソッドを使用してサーバータイプを確認
    result = await client.get_status()
    
    if "error" in result:
        raise RuntimeError(result['error'])
    
    # サーバータイプがTwilogServerかどうか確認
    server_type = result.get('server_type', '')
    if server_type != 'TwilogServer':
        raise RuntimeError(f"サーバータイプが 'TwilogServer' ではありません: {server_type}")

def show_help():
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

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Twilogリモート検索システム")
    parser.add_argument("csv_file", nargs="?", default="twilog.csv",
                        help="CSVファイルのパス（デフォルト: twilog.csv）")
    parser.add_argument("-s", "--server-url", default="ws://localhost:8765",
                        help="TwilogサーバーのWebSocket URL（デフォルト: ws://localhost:8765）")
    args = parser.parse_args()
    
    # 検索システムの初期化
    client = TwilogClient(args.server_url)
    search = SearchEngine(args.csv_file)
    try:
        print("WebSocketサーバーへの接続を確認中...")
        asyncio.run(test_websocket_connection(client))
        print("WebSocketサーバー接続成功")
    except Exception as e:
        print(f"WebSocketサーバー接続失敗: {e}")
        print("WebSocketサーバーが利用できません。twilog_server.py start でデーモンを起動してください。")
        sys.exit(1)

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
                show_help()
                continue
            elif command == "user":
                show_user_filter_menu(search.user_filter_settings)
                continue
            elif command == "date":
                show_date_filter_menu(search.date_filter_settings)
                continue
            elif command == "top":
                show_top_k_menu(search.top_k_settings)
                continue
            elif command in ["exit", "quit", "q"]:
                print("プログラムを終了します")
                return
            else:
                print(f"エラー: 不明なコマンド '{command}'")
                search._show_help()
                continue
        
        # 検索実行
        vector_search_results = asyncio.run(client.vector_search(query))["data"]
        results = []
        for result in search.search(vector_search_results):
            results.append(result)
            if len(results) >= search.top_k_settings.get_top_k():
                break
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 結果表示
        console = Console()
        rank_width = len(str(search.top_k_settings.get_top_k()))
        
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
