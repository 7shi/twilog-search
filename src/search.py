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
from user_info import UserInfo


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

def show_results(results, start_index, top_k, total_count, query):
    """検索結果を表示"""
    if not results:
        print("結果が見つかりませんでした")
        return
    
    # 表示範囲の計算
    end_index = min(start_index + top_k, len(results))
    display_results = results[start_index:end_index]
    
    # 結果表示
    console = Console()
    rank_width = len(str(total_count))  # 総件数に基づいて桁数を決定
    
    for i, result in enumerate(display_results):
        rank = start_index + i + 1  # 1ベースのランク
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
    range_text = f"{start_index + 1}-{end_index}/{total_count}件"
    console.print(Rule(f"検索結果: {range_text} (クエリ: '{query}')", style="dim"))


def show_help():
    """ヘルプメッセージを表示"""
    print("\n=== ヘルプ ===")
    print("特殊コマンド:")
    print("  /help, /?  - このヘルプを表示")
    print("  /user  - ユーザーフィルタリング設定")
    print("  /date  - 日付フィルタリング設定")
    print("  /top   - 表示件数設定")
    print("  /mode  - 検索モード設定")
    print("  /next  - 次の検索結果を表示")
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
    
    # ユーザー一覧を取得してUserInfoインスタンスを作成
    try:
        user_list = asyncio.run(client.get_user_list())
        print(f"ユーザー一覧取得完了: {len(user_list)}件")
    except Exception as e:
        print(f"ユーザー一覧取得エラー: {e}")
        user_list = []
    
    user_info = UserInfo(user_list)
    
    # 検索結果の状態管理
    last_search_results = []
    current_display_index = 0
    last_query = ""
    
    print("リモート検索システム準備完了")
    print()
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
                show_user_filter_menu(search_settings.user_filter, user_info)
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
            elif command == "next":
                # 前回の検索結果がない場合
                if not last_search_results:
                    print("検索結果がありません。先に検索を実行してください。")
                    continue
                
                # 次の表示範囲が存在するかチェック
                if current_display_index >= len(last_search_results):
                    print("これ以上表示できる結果がありません。")
                    continue
                
                # 次の結果を表示
                top_k = search_settings.top_k.get_top_k()
                show_results(last_search_results, current_display_index, top_k, len(last_search_results), last_query)
                
                # 表示位置を更新
                current_display_index += top_k
                continue
            elif command in ["exit", "quit", "q"]:
                print("プログラムを終了します")
                return
            else:
                print(f"エラー: 不明なコマンド '{command}'")
                show_help()
                continue
        
        # 検索実行（常に100件取得）
        try:
            mode = search_settings.mode_settings.get_mode()
            weights = search_settings.mode_settings.get_weights()
            
            # 検索設定をコピーして常に100件取得するように変更
            search_settings_copy = SearchSettings()
            search_settings_copy.user_filter = search_settings.user_filter
            search_settings_copy.date_filter = search_settings.date_filter
            search_settings_copy.mode_settings = search_settings.mode_settings
            search_settings_copy.top_k.set_top_k(100)  # 常に100件取得
            
            results = asyncio.run(client.search_similar(query, search_settings_copy, mode, weights))
        except Exception as e:
            print(f"検索エラー: {e}")
            continue
        
        if not results:
            print("結果が見つかりませんでした")
            continue
        
        # 検索結果の状態を更新
        last_search_results = results
        current_display_index = 0
        last_query = query
        
        # 結果表示
        top_k = search_settings.top_k.get_top_k()
        show_results(last_search_results, current_display_index, top_k, len(last_search_results), last_query)
        
        # 表示位置を更新
        current_display_index += top_k

if __name__ == "__main__":
    main()
