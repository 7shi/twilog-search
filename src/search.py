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
from settings_ui import show_user_filter_menu, show_date_filter_menu, show_top_k_menu, show_mode_menu, show_view_mode_menu
from settings import DEFAULT_MODE, DEFAULT_VIEW_MODE, SearchSettings
from twilog_client import TwilogClient
from safe_input import safe_text_input
from user_info import UserInfo
from command import CommandHandler

# グローバル変数
search_settings = None
user_info = None
last_search_results = []
current_display_index = 0
last_query = ""
should_exit = False

# グローバルコマンドハンドラー
command_handler = CommandHandler()
command = command_handler.command


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


def show_single_result(result, rank, total_count, show_summary_reasoning=False):
    """1つの検索結果をPanel形式で表示"""
    console = Console()
    rank_width = len(str(total_count))  # 総件数に基づいて桁数を決定
    
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
        tag_text = f" #{' #'.join(tags)}"
        header += f" [bright_magenta]{tag_text}[/bright_magenta]"
    
    # Panel内容を構築
    content = post_info.get('content', '').strip()
    panel_content = content
    
    # 詳細モードの場合はsummary+reasoningを追加
    if show_summary_reasoning:
        summary = post_info.get('summary', '')
        reasoning = post_info.get('reasoning', '')
        
        if summary:
            panel_content += f"\n[bold blue]────────── {summary.strip()} ──────────[/bold blue]"
        
        if reasoning:
            panel_content += f"\n{reasoning.strip()}"
    
    # パネル表示
    panel = Panel(
        panel_content,
        title=header,
        title_align="left",
        subtitle=f"[blue]{post_info['url']}[/blue]",
        subtitle_align="right",
        border_style="bright_blue",
        padding=(0, 1)
    )
    
    console.print()  # パネル間のスペース
    console.print(panel)


def show_results_panel(results, start_index, top_k, total_count, query, show_summary_reasoning=False):
    """検索結果をPanel形式で表示（通常モード・詳細モード共通）"""
    if not results:
        print("結果が見つかりませんでした")
        return
    
    # 表示範囲の計算
    end_index = min(start_index + top_k, len(results))
    display_results = results[start_index:end_index]
    
    # 結果表示
    for i, result in enumerate(display_results):
        rank = start_index + i + 1  # 1ベースのランク
        show_single_result(result, rank, total_count, show_summary_reasoning)
    
    # 検索結果終了のセパレーター
    console = Console()
    console.print()
    range_text = f"{start_index + 1}-{end_index}/{total_count}件"
    mode_text = "詳細モード" if show_summary_reasoning else "通常"
    console.print(Rule(f"検索結果（{mode_text}）: {range_text} (クエリ: '{query}')", style="dim"))


def show_results_list(results, total_count, query):
    """検索結果を一覧形式で表示（100件固定）"""
    if not results:
        print("結果が見つかりませんでした")
        return
    
    console = Console()
    rank_width = len(str(total_count))  # 総件数に基づいて桁数を決定
    
    # 100件固定で表示
    display_count = min(100, len(results))
    
    for i, result in enumerate(results[:display_count]):
        rank = i + 1  # 1ベースのランク
        similarity = result.get('score', 0.0)
        post_info = result.get('post', {})
        user = post_info.get('user', 'unknown')
        summary = post_info.get('summary', '')
        
        # タグ情報を整形
        tags = post_info.get('tags', [])
        tag_text = f" #{' #'.join(tags)}" if tags else ""
        
        # summaryが長い場合は切り詰める
        if len(summary) > 60:
            summary = summary[:57] + "..."
        
        # 1行形式で表示
        line = (
            f"[bold cyan]{rank:{rank_width}d}[/bold cyan] "
            f"[bold green]{similarity:.5f}[/bold green] "
            f"[yellow][{post_info.get('timestamp', '')}][/yellow] "
            f"[bold blue]{user}[/bold blue] "
            f"{summary}"
            f"[bright_magenta]{tag_text}[/bright_magenta]"
        )
        
        console.print(line)
    
    # 検索結果終了のセパレーター
    console.print()
    range_text = f"1-{display_count}/{total_count}件"
    console.print(Rule(f"検索結果（一覧モード）: {range_text} (クエリ: '{query}')", style="dim"))


def show_results(results, start_index, top_k, total_count, query, view_mode="normal"):
    """検索結果を指定された表示モードで表示"""
    if view_mode == "list":
        show_results_list(results, total_count, query)
    elif view_mode == "detail":
        show_results_panel(results, start_index, top_k, total_count, query, show_summary_reasoning=True)
    else:  # normal
        show_results_panel(results, start_index, top_k, total_count, query, show_summary_reasoning=False)


@command(["help", "?"], "このヘルプを表示")
def command_help(handler):
    """ヘルプコマンド"""
    handler.show_help()


@command(["user"], "ユーザーフィルタリング設定")
def command_user(handler):
    """ユーザーフィルタリング設定コマンド"""
    show_user_filter_menu(search_settings.user_filter, user_info)


@command(["date"], "日付フィルタリング設定")
def command_date(handler):
    """日付フィルタリング設定コマンド"""
    show_date_filter_menu(search_settings.date_filter)


@command(["top"], "表示件数設定")
def command_top(handler):
    """表示件数設定コマンド"""
    show_top_k_menu(search_settings.top_k)


@command(["mode"], "検索モード設定")
def command_mode(handler):
    """検索モード設定コマンド"""
    show_mode_menu(search_settings.mode_settings)


@command(["view"], "表示モード設定")
def command_view(handler):
    """表示モード設定コマンド"""
    show_view_mode_menu(search_settings.view_mode)


@command(["next"], "次の検索結果を表示")
def command_next(handler):
    """次の検索結果表示コマンド"""
    global current_display_index
    
    # 前回の検索結果がない場合
    if not last_search_results:
        print("検索結果がありません。先に検索を実行してください。")
        return
    
    # 一覧モードの場合はページネーション無効
    if search_settings.view_mode.get_view_mode() == "list":
        print("一覧モードではページネーション機能は利用できません（100件固定表示）。")
        return
    
    # 次の表示範囲が存在するかチェック
    if current_display_index >= len(last_search_results):
        print("これ以上表示できる結果がありません。")
        return
    
    # 次の結果を表示
    top_k = search_settings.top_k.get_top_k()
    view_mode = search_settings.view_mode.get_view_mode()
    show_results(
        last_search_results, 
        current_display_index, 
        top_k, 
        len(last_search_results), 
        last_query,
        view_mode
    )
    
    # 表示位置を更新
    current_display_index += top_k


@command(["details", "d"], "指定ランクの詳細表示")
def command_details(handler, args_str):
    """指定ランクの詳細表示コマンド"""
    # 前回の検索結果がない場合
    if not last_search_results:
        print("検索結果がありません。先に検索を実行してください。")
        return
    
    # 引数の確認
    if not args_str.strip():
        print("使用方法: /details <ランク指定> または /d <ランク指定>")
        print("例: /d 1,5  /d 23-50  /d 1-3,7,10-15")
        return
    
    # 範囲指定を解析（CommandHandlerのメソッドを使用）
    ranks = handler.parse_range_specification(args_str.strip())
    
    if not ranks:
        print("有効なランク指定がありません")
        print("例: /d 1,5  /d 23-50  /d 1-3,7,10-15")
        return
    
    # 詳細表示
    total_count = len(last_search_results)
    valid_ranks = []
    for rank in ranks:
        if 1 <= rank <= total_count:
            valid_ranks.append(rank)
    
    if not valid_ranks:
        print(f"有効なランク番号がありません（1-{total_count}の範囲で指定してください）")
        return
    
    # 各ランクの結果を詳細表示
    for rank in valid_ranks:
        result = last_search_results[rank - 1]  # 1ベースから0ベースに変換
        show_single_result(result, rank, total_count, show_summary_reasoning=True)
    
    # 検索結果終了のセパレーター
    console = Console()
    console.print()
    console.print(Rule(f"詳細表示: {len(valid_ranks)}件 (クエリ: '{last_query}')", style="dim"))


@command(["exit", "quit", "q"], "プログラム終了")
def command_exit(handler):
    """プログラム終了コマンド"""
    global should_exit
    should_exit = True
    print("プログラムを終了します")


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
    initial_view_mode = DEFAULT_VIEW_MODE
    data_stats = status.get('data_stats', {})
    if data_stats.get('total_summaries', 0) > 0:
        initial_mode = "maximum"
        initial_view_mode = "list"
    
    # グローバル変数の初期化
    global search_settings, user_info
    search_settings = SearchSettings()
    search_settings.mode_settings.set_mode(initial_mode)
    search_settings.view_mode.set_view_mode(initial_view_mode)
    
    # ユーザー一覧を取得してUserInfoインスタンスを作成
    try:
        user_list = asyncio.run(client.get_user_list())
        print(f"ユーザー一覧取得完了: {len(user_list)}件")
    except Exception as e:
        print(f"ユーザー一覧取得エラー: {e}")
        user_list = []
    
    user_info = UserInfo(user_list)
    
    # コマンドハンドラーの初期化（グローバル変数を使用）
    # command_handler = CommandHandler() # 既にグローバルで初期化済み
    
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
        view_status = search_settings.view_mode.format_status()
        
        if user_status != "すべてのユーザー":
            restrictions.append(f"ユーザー: {user_status}")
        if date_status != "すべての日付":
            restrictions.append(f"日付: {date_status}")
        if mode_status != DEFAULT_MODE:
            restrictions.append(f"モード: {mode_status}")
        if view_status != DEFAULT_VIEW_MODE:
            restrictions.append(f"表示: {view_status}")
        
        if restrictions:
            console = Console()
            console.print(f"[bold blue][設定][/bold blue] {' | '.join(restrictions)}")
        
        try:
            # コマンド補完を有効にして入力
            with command_handler.setup_completion():
                query = safe_text_input("> ", "main", handle_eof=False)
            if not query:
                continue
            query = query.strip()
        except EOFError:
            # Ctrl+Dの場合は終了
            print()
            break
        
        # コマンド処理
        if command_handler.execute(query):
            if should_exit:
                break
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
        global last_search_results, current_display_index, last_query
        last_search_results = results
        current_display_index = 0
        last_query = query
        
        # 結果表示
        top_k = search_settings.top_k.get_top_k()
        view_mode = search_settings.view_mode.get_view_mode()
        show_results(results, 0, top_k, len(results), query, view_mode)
        
        # 表示位置を更新（一覧モードは100件固定表示のためページネーション無し）
        if view_mode != "list":
            current_display_index += top_k

if __name__ == "__main__":
    main()
