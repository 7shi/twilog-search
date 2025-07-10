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
    
    # SearchEngine初期化状況も確認
    search_engine_ready = result.get('search_engine_ready', False)
    if not search_engine_ready:
        raise RuntimeError("SearchEngineが初期化されていません")

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
    parser.add_argument("-s", "--server-url", default="ws://localhost:8765",
                        help="TwilogサーバーのWebSocket URL（デフォルト: ws://localhost:8765）")
    args = parser.parse_args()
    
    # 検索システムの初期化
    client = TwilogClient(args.server_url)
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
                print("ユーザーフィルタリング機能は現在利用できません")
                continue
            elif command == "date":
                print("日付フィルタリング機能は現在利用できません")
                continue
            elif command == "top":
                print("表示件数設定機能は現在利用できません")
                continue
            elif command in ["exit", "quit", "q"]:
                print("プログラムを終了します")
                return
            else:
                print(f"エラー: 不明なコマンド '{command}'")
                show_help()
                continue
        
        # 検索実行
        try:
            results = asyncio.run(client.search_similar(query))
        except Exception as e:
            print(f"検索エラー: {e}")
            continue
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 結果表示
        console = Console()
        rank_width = len(str(10))  # デフォルト10件表示
        
        for rank, similarity, post_info in results:
            user = post_info.get('user', 'unknown')
            
            # ヘッダー情報（色付き）
            header = f"[bold cyan]{rank:{rank_width}d}[/bold cyan]: [bold green]{similarity:.5f}[/bold green] [bold blue]{user}[/bold blue] [yellow][{post_info.get('timestamp', '')}][/yellow]"
            
            # URLがある場合は追加
            if post_info.get('url'):
                header += f" [dim]{post_info['url']}[/dim]"
            
            # パネル表示
            panel = Panel(
                post_info.get('content', '').rstrip(),
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
