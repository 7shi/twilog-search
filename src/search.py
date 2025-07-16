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
from settings_ui import show_user_filter_menu, show_date_filter_menu, show_top_k_menu, show_mode_menu
from settings import DEFAULT_MODE, SearchSettings
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
    
    return result

def show_help():
    """ヘルプメッセージを表示"""
    print("\n=== ヘルプ ===")
    print("特殊コマンド:")
    print("  /help, /?  - このヘルプを表示")
    print("  /user  - ユーザーフィルタリング設定")
    print("  /date  - 日付フィルタリング設定")
    print("  /top   - 表示件数設定")
    print("  /mode  - 検索モード設定")
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
        status = asyncio.run(test_websocket_connection(client))
        print("WebSocketサーバー接続成功")
    except Exception as e:
        print(f"WebSocketサーバー接続失敗: {e}")
        print("WebSocketサーバーが利用できません。twilog_server.py start でデーモンを起動してください。")
        sys.exit(1)
    
    # 検索設定の初期化（data_statsに基づいてモードを決定）
    initial_mode = DEFAULT_MODE
    data_stats = status.get('data_stats', {})
    if data_stats.get('total_summaries', 0) > 0:
        initial_mode = "maximum"
    
    search_settings = SearchSettings()
    search_settings.mode_settings.set_mode(initial_mode)

    print(f"リモート検索システム準備完了")
    print("検索クエリを入力してください")
    print("特殊コマンド: /help でヘルプ表示")
    
    # 対話的な検索ループ
    while True:
        print()
        
        # 現在の制限を表示
        restrictions = []
        user_status = search_settings.user_filter.format_status()
        date_status = search_settings.date_filter.format_status()
        mode_status = search_settings.mode_settings.format_status()
        
        if user_status != "すべてのユーザー":
            restrictions.append(f"ユーザー: {user_status}")
        if date_status != "すべての日付":
            restrictions.append(f"日付: {date_status}")
        if mode_status != DEFAULT_MODE:
            restrictions.append(f"モード: {mode_status}")
        
        if restrictions:
            print(f"[制限] {' | '.join(restrictions)}")
        
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
                show_user_filter_menu(search_settings.user_filter, client.suggest_users)
                continue
            elif command == "date":
                show_date_filter_menu(search_settings.date_filter)
                continue
            elif command == "top":
                show_top_k_menu(search_settings.top_k)
                continue
            elif command == "mode":
                show_mode_menu(search_settings.mode_settings)
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
            mode = search_settings.mode_settings.get_mode()
            weights = search_settings.mode_settings.get_weights()
            results = asyncio.run(client.search_similar(query, search_settings, mode, weights))
        except Exception as e:
            print(f"検索エラー: {e}")
            continue
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 結果表示
        console = Console()
        rank_width = len(str(10))  # デフォルト10件表示
        
        for result in results:
            rank = result.get('rank', 0)
            similarity = result.get('score', 0.0)
            post_info = result.get('post', {})
            user = post_info.get('user', 'unknown')
            
            # ヘッダー情報（色付き）
            header  = f"[bold cyan]{rank:{rank_width}d}[/bold cyan]:"           # ランク
            header += f" [bold green]{similarity:.5f}[/bold green]"             # 類似度
            header += f" [yellow][{post_info.get('timestamp', '')}][/yellow]"   # 日時
            header += f" [bold blue]{user}[/bold blue]"                         # ユーザー
            
            # タグがある場合は追加
            tags = post_info.get('tags', [])
            if tags:
                header += f" [bright_magenta][{' '.join(tags)}][/bright_magenta]"
            
            # パネル表示
            panel = Panel(
                post_info['content'].strip(),
                title=header,
                title_align="left",
                subtitle=f"[blue]{post_info['url']}[/blue]",
                subtitle_align="right",
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
