#!/usr/bin/env python3
"""
設定UI機能を提供するモジュール
"""

import asyncio
from rich.console import Console
from simple_term_menu import TerminalMenu
from safe_input import safe_text_input, safe_number_input, safe_date_input, yes_no_menu, safe_text_input_with_user_completion
from settings import UserFilterSettings, DateFilterSettings, TopKSettings, SearchModeSettings, ViewModeSettings


def _add_menu_option(options: list, index: int, is_current: bool, text: str) -> None:
    """
    メニューオプションを追加する共通関数
    
    Args:
        options: オプションリスト
        index: メニュー番号
        is_current: 現在選択中かどうか
        text: オプション説明文
    """
    if is_current:
        options.append(f"[{index}] ● {text}")
    else:
        options.append(f"[{index}] {text}")


def _show_user_suggestions_menu(missing_user: str, suggestions: list, suggest_users_func) -> str:
    """
    ユーザー候補選択メニューを表示（ループ形式）
    
    Args:
        missing_user: 存在しないユーザー名
        suggestions: 類似ユーザー候補のリスト
        suggest_users_func: suggest_users関数オブジェクト
        
    Returns:
        選択されたユーザー名、または None（キャンセル）、または "DELETE"（削除）
    """
    console = Console()
    current_user = missing_user
    current_suggestions = suggestions
    
    while True:
        console.print(f"\n[yellow]ユーザー '{current_user}' が見つかりません[/yellow]")
        
        # 選択肢を構築
        options = []
        has_suggestions = current_suggestions is not None and len(current_suggestions) > 0
        
        if not has_suggestions:
            if current_suggestions is None:
                console.print("[red]候補が取得できませんでした[/red]")
            else:
                console.print("[red]類似ユーザーの候補がありません[/red]")
            suggestion_count = 0
        else:
            # 候補がある場合は通常の選択肢
            for i, user in enumerate(current_suggestions, 1):
                options.append(f"[{i}] {user}")
            suggestion_count = len(current_suggestions)
        
        # 特別な選択肢を追加
        options.append(f"[{suggestion_count + 1}] 直接入力")
        options.append(f"[{suggestion_count + 2}] 削除")
        options.append(f"[0] 戻る")
        
        terminal_menu = TerminalMenu(
            options,
            title=f"'{current_user}' の代替候補を選択してください:",
            show_search_hint=True
        )
        
        choice_index = terminal_menu.show()
        
        if choice_index is None:
            return None  # Escキャンセル
        elif choice_index == len(options) - 1:  # [0] 戻る
            return None  # 戻る
        elif choice_index < suggestion_count:
            selected_user = current_suggestions[choice_index]
            console.print(f"[green]'{selected_user}' を選択しました[/green]")
            return selected_user  # 候補ユーザーを選択
        elif choice_index == suggestion_count:
            # 直接入力（補完機能は使用しない - 候補選択時のため）
            new_user = safe_text_input(f"'{current_user}' の代わりに使用するユーザー名を入力: ", "user")
            if new_user is None or new_user.strip() == "":
                # 空欄またはCtrl+Dの場合、メニューに戻る（continueでループ継続）
                continue
            
            new_user = new_user.strip()
            
            # 新しいユーザー名で再度suggest_usersを呼び出し
            if suggest_users_func is not None:
                try:
                    suggestions_result = suggest_users_func([new_user])
                    if new_user in suggestions_result:
                        # 新しいユーザーも存在しない場合、候補を更新してループ継続
                        current_user = new_user
                        current_suggestions = suggestions_result[new_user]
                        continue
                    else:
                        # 新しいユーザーが存在する場合
                        console.print(f"[green]'{new_user}' を選択しました[/green]")
                        return new_user
                except Exception as e:
                    console.print(f"[red]ユーザー候補取得エラー: {e}[/red]")
                    # エラー時は候補を取得できなかった状態でループ継続
                    current_user = new_user
                    current_suggestions = None
                    continue
            else:
                # suggest_users_funcが提供されていない場合はそのまま使用
                console.print(f"[green]'{new_user}' を選択しました[/green]")
                return new_user
        elif choice_index == suggestion_count + 1:  # 削除
            return "DELETE"  # 削除を選択


def _handle_user_input_with_suggestions(
    prompt: str, 
    history: str, 
    suggest_users_func, 
    current_users_func, 
    filter_type: str,
    user_info=None
) -> tuple:
    """
    ユーザー入力を処理し、存在しないユーザーに対して候補を表示
    
    Args:
        prompt: 入力プロンプト
        history: 履歴キー
        suggest_users_func: suggest_users関数オブジェクト
        current_users_func: 現在の設定値を取得する関数
        filter_type: フィルタータイプ（"includes" or "excludes"）
        user_info: ユーザー情報インスタンス（オプション）
        
    Returns:
        (success: bool, users: list or None)
    """
    # ユーザー一覧が提供されている場合は補完機能付きの入力を使用
    if user_info:
        users_input = safe_text_input_with_user_completion(prompt, history, user_info)
    else:
        users_input = safe_text_input(prompt, history)
    
    if users_input is None:
        return False, None  # Ctrl+Dの場合
    elif users_input.strip():
        users = [user.strip() for user in users_input.split(',') if user.strip()]
        
        # suggest_users_funcが提供されている場合、ユーザー存在チェック
        if suggest_users_func is not None:
            try:
                suggestions = suggest_users_func(users)
                
                # 存在しないユーザーがある場合
                if suggestions:
                    console = Console()
                    corrected_users = []
                    
                    for user in users:
                        if user in suggestions:
                            # 候補選択メニューを表示
                            choice = _show_user_suggestions_menu(user, suggestions[user], suggest_users_func)
                            if choice is None:
                                # キャンセル
                                return False, None
                            elif choice == "DELETE":
                                # このユーザーを削除（リストに追加しない）
                                continue
                            else:
                                corrected_users.append(choice)
                        else:
                            # 存在するユーザーはそのまま追加
                            corrected_users.append(user)
                    
                    users = corrected_users
                
            except Exception as e:
                console = Console()
                console.print(f"[red]ユーザー候補取得エラー: {e}[/red]")
                console.print("[yellow]元の入力をそのまま使用します[/yellow]")
        
        return True, users
    else:
        # 無入力の場合、値を消去するか確認
        current_users = current_users_func()
        if current_users:
            should_clear = yes_no_menu(
                f"現在の{filter_type}設定({len(current_users)}人)を消去しますか？",
                default_yes=False
            )
            if should_clear:
                return True, []  # 空のリストで消去
        return False, None  # メニューに戻る


def show_user_filter_menu(settings: UserFilterSettings, user_info=None):
    """ユーザーフィルタリングメニューを表示"""
    while True:
        print(f"\n=== ユーザーフィルタリング設定 ===")
        print(f"現在の設定: {settings.format_status()}")
        
        options = []
        
        # 當前の設定状態を表示しながらメニュー項目を作成
        is_none = not settings.filter_settings
        _add_menu_option(options, 1, is_none, "none（すべてのユーザー）")
        _add_menu_option(options, 2, settings.has_includes(), "includes（指定ユーザーのみ）")
        _add_menu_option(options, 3, settings.has_excludes(), "excludes（指定ユーザーを除外）")
        _add_menu_option(options, 4, settings.has_threshold_min(), "threshold min（投稿数下限）")
        _add_menu_option(options, 5, settings.has_threshold_max(), "threshold max（投稿数上限）")
        _add_menu_option(options, 0, False, "戻る")
        
        terminal_menu = TerminalMenu(
            options,
            title="フィルター方式を選択してください:",
            show_search_hint=True
        )
        
        choice_index = terminal_menu.show()
        
        if choice_index is None:
            return
        
        if choice_index == len(options) - 1:  # [0] 戻る
            return
        
        if choice_index == 0:  # none
            settings.set_none()
            print("フィルタリングを無効にしました")
            return  # noneは即座に抜ける
            
        elif choice_index == 1:  # includes
            if _handle_includes(settings, user_info):
                return  # includes設定完了時は即座に抜ける
            
        elif choice_index == 2:  # excludes
            if _handle_excludes(settings, user_info):
                return  # excludes設定完了時は即座に抜ける
            
        elif choice_index == 3:  # threshold min
            _handle_threshold_min(settings)
            
        elif choice_index == 4:  # threshold max
            _handle_threshold_max(settings)


def _handle_includes(settings: UserFilterSettings, user_info=None):
    """includes設定の処理"""
    suggest_users_func = user_info.suggest_users if user_info else None
    success, users = _handle_user_input_with_suggestions(
        "ユーザー名をコンマ区切りで入力: ",
        "user",
        suggest_users_func,
        lambda: settings.get_includes() if settings.has_includes() else [],
        "includes",
        user_info
    )
    
    if not success:
        return False  # メニューに戻る
    
    if users is not None:
        if len(users) > 0:
            # includes設定時は他の設定をすべてクリア
            settings.set_includes(users)
            console = Console()
            console.print(f"[green]includes設定: {len(users)}人のユーザーを対象[/green]")
            return True  # includes設定完了
        else:
            # 空のリストで消去
            settings.clear_includes()
            console = Console()
            console.print(f"[green]includes設定を消去しました[/green]")
            console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
    
    return False  # メニューに戻る


def _handle_excludes(settings: UserFilterSettings, user_info=None):
    """excludes設定の処理"""
    suggest_users_func = user_info.suggest_users if user_info else None
    success, users = _handle_user_input_with_suggestions(
        "除外ユーザー名をコンマ区切りで入力: ",
        "user",
        suggest_users_func,
        lambda: settings.get_excludes() if settings.has_excludes() else [],
        "excludes",
        user_info
    )
    
    if not success:
        return False  # メニューに戻る
    
    if users is not None:
        if len(users) > 0:
            # excludes設定時は他の設定をすべてクリア
            settings.set_excludes(users)
            console = Console()
            console.print(f"[green]excludes設定: {len(users)}人のユーザーを除外[/green]")
            return True  # excludes設定完了
        else:
            # 空のリストで消去
            settings.clear_excludes()
            console = Console()
            console.print(f"[green]excludes設定を消去しました[/green]")
            console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
    
    return False  # メニューに戻る


def _handle_threshold_min(settings: UserFilterSettings):
    """threshold min設定の処理"""
    min_posts = safe_number_input(
        "投稿数下限を入力: ",
        history="threshold",
        min_val=1
    )
    
    if min_posts is None:
        # Ctrl+Dの場合、何も変更せずにメニューに戻る
        return
    elif min_posts == "":
        # 無入力の場合、値を消去するか確認
        if settings.has_threshold_min():
            current_value = settings.get_threshold_min()
            should_clear = yes_no_menu(
                f"現在のthreshold min設定({current_value})を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_threshold_min()
                console.print(f"[green]threshold min設定を消去しました[/green]")
                console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
        # 回答に関わらずメニューに戻る
        return
    
    # 上限との整合性チェック
    console = Console()
    if settings.has_threshold_max():
        max_posts = settings.get_threshold_max()
        if min_posts >= max_posts:
            console.print(f"[yellow]threshold max設定({max_posts})がthreshold min設定({min_posts})と矛盾するため削除しました[/yellow]")
    
    # includes/excludesを削除し、threshold系のみ保持
    settings.set_threshold_min(min_posts)
        
    console.print(f"[green]threshold min={min_posts}: 投稿数{min_posts}以上のユーザーを対象[/green]")
    console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
    # threshold minはメニューに戻る（continueで次のループへ）


def _handle_threshold_max(settings: UserFilterSettings):
    """threshold max設定の処理"""
    # 下限が設定されている場合は、それより大きい値を要求
    min_threshold = None
    if settings.has_threshold_min():
        min_threshold = settings.get_threshold_min() + 1
    
    max_posts = safe_number_input(
        "投稿数上限を入力: ",
        history="threshold",
        min_val=min_threshold or 1
    )
    
    if max_posts is None:
        # Ctrl+Dの場合、何も変更せずにメニューに戻る
        return
    elif max_posts == "":
        # 無入力の場合、値を消去するか確認
        if settings.has_threshold_max():
            current_value = settings.get_threshold_max()
            should_clear = yes_no_menu(
                f"現在のthreshold max設定({current_value})を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_threshold_max()
                console.print(f"[green]threshold max設定を消去しました[/green]")
                console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
        # 回答に関わらずメニューに戻る
        return
    
    # 下限との整合性チェック
    console = Console()
    if settings.has_threshold_min():
        min_posts = settings.get_threshold_min()
        if max_posts <= min_posts:
            console.print(f"[yellow]threshold min設定({min_posts})がthreshold max設定({max_posts})と矛盾するため削除しました[/yellow]")
    
    # includes/excludesを削除し、threshold系のみ保持
    settings.set_threshold_max(max_posts)
        
    console.print(f"[green]threshold max={max_posts}: 投稿数{max_posts}以下のユーザーを対象[/green]")
    console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
    # threshold maxはメニューに戻る（continueで次のループへ）


def show_date_filter_menu(settings: DateFilterSettings):
    """日付フィルタリングメニューを表示"""
    print(f"\n=== 日付フィルタリング設定 ===")
    
    while True:
        print(f"現在の設定: {settings.format_status()}")
        options = []
        
        # 當前の設定状態を表示しながらメニュー項目を作成
        is_all = not settings.filter_settings
        _add_menu_option(options, 1, is_all, "all（すべての日付）")
        _add_menu_option(options, 2, settings.has_from(), "from（開始日時を設定）")
        _add_menu_option(options, 3, settings.has_to(), "to（終了日時を設定）")
        _add_menu_option(options, 0, False, "戻る")
        terminal_menu = TerminalMenu(
            options,
            title="日付フィルター方式を選択してください:",
            show_search_hint=True
        )
        choice_index = terminal_menu.show()
        
        if choice_index is None:
            return
        
        if choice_index == len(options) - 1:  # [0] 戻る
            return
        
        if choice_index == 0:  # all
            settings.set_all()
            print("日付フィルタリングを無効にしました")
            return  # allは即座に抜ける
            
        elif choice_index == 1:  # from
            _handle_from_date(settings)
            
        elif choice_index == 2:  # to
            _handle_to_date(settings)


def _handle_from_date(settings: DateFilterSettings):
    """from日付設定の処理"""
    from_date = safe_date_input("開始日時を入力: ", "date_input")
    
    if from_date is None:
        return  # Ctrl+Dの場合はメニューに戻る
    elif from_date == "":
        # 無入力の場合、値を消去するか確認
        if settings.has_from():
            current_value = settings.get_from()[:10]
            should_clear = yes_no_menu(
                f"現在のfrom設定({current_value})を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_from()
                console.print(f"[green]from設定を消去しました[/green]")
    else:
        # 適切な日付が入力された場合の処理
        console = Console()
        # toとの矛盾チェック
        if settings.has_to():
            to_date = settings.get_to()
            if from_date >= to_date:
                console.print(f"[yellow]to設定({to_date[:10]})がfrom設定({from_date[:10]})と矛盾するため削除しました[/yellow]")
        
        settings.set_from(from_date)
        console.print(f"[green]from設定: {from_date}以降の投稿を対象[/green]")
    # from設定後はメニューに戻る


def _handle_to_date(settings: DateFilterSettings):
    """to日付設定の処理"""
    to_date = safe_date_input("終了日時を入力: ", "date_input")
    
    if to_date is None:
        return  # Ctrl+Dの場合はメニューに戻る
    elif to_date == "":
        # 無入力の場合、値を消去するか確認
        if settings.has_to():
            current_value = settings.get_to()[:10]
            should_clear = yes_no_menu(
                f"現在のto設定({current_value})を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_to()
                console.print(f"[green]to設定を消去しました[/green]")
    else:
        # 適切な日付が入力された場合の処理
        console = Console()
        # fromとの矛盾チェック
        if settings.has_from():
            from_date = settings.get_from()
            if from_date >= to_date:
                console.print(f"[yellow]from設定({from_date[:10]})がto設定({to_date[:10]})と矛盾するため削除しました[/yellow]")
        
        settings.set_to(to_date)
        console.print(f"[green]to設定: {to_date}以前の投稿を対象[/green]")
    # to設定後はメニューに戻る


def show_top_k_menu(settings: TopKSettings):
    """表示件数設定メニューを表示"""
    console = Console()
    console.print(f"\n[bold]=== 表示件数設定 ===[/bold]")
    console.print(f"現在の設定: {settings.get_top_k()}件")
    
    new_top_k = safe_number_input(
        "表示件数を入力: ",
        history="top_k",
        min_val=1,
        max_val=100,
        default=settings.get_top_k()
    )
    
    if new_top_k:
        settings.set_top_k(new_top_k)
        console.print(f"[green]表示件数を{new_top_k}件に設定しました[/green]")


def show_mode_menu(settings: SearchModeSettings):
    """検索モード設定メニューを表示"""
    console = Console()
    
    # モード選択肢（最適化後の6種類）
    mode_options = [
        ("content", "投稿内容のベクトル検索"),
        ("reasoning", "タグ付け理由のベクトル検索"),
        ("summary", "要約のベクトル検索"),
        ("average", "3空間の平均（重み付き対応）"),
        ("maximum", "3空間の最高類似度（寛容な検索）"),
        ("minimum", "3空間の最低類似度（厳格な検索）")
    ]
    
    while True:
        console.print(f"\n[bold]=== 検索モード設定 ===[/bold]")
        console.print(f"現在の設定: {settings.format_status()}")
        
        # メニューオプション作成
        menu_items = []
        for i, (mode, description) in enumerate(mode_options, 1):
            if mode == settings.get_mode():
                menu_items.append(f"[{i}] ● {mode}: {description}")
            else:
                menu_items.append(f"[{i}] {mode}: {description}")
        
        # averageモードの場合のweights設定オプション
        if settings.get_mode() == "average":
            menu_items.append(f"[{len(mode_options)+1}] weights: 重み設定の変更")
        
        menu_items.append(f"[0] 戻る")
        
        terminal_menu = TerminalMenu(menu_items, title="モードを選択してください:", show_search_hint=True)
        choice = terminal_menu.show()
        
        if choice is None:  # ESCキー
            break
        elif choice == len(menu_items) - 1:  # [0] 戻る
            break
        elif choice < len(mode_options):  # モード選択
            mode, _ = mode_options[choice]
            settings.set_mode(mode)
            console.print(f"[green]検索モードを '{mode}' に設定しました[/green]")
            
            # averageモードの場合は重み設定も表示
            if mode == "average":
                if _show_weights_submenu(settings):
                    break  # 重み設定完了した場合はメニューから抜ける
                # Falseの場合はトップメニューに戻る（continueで次のループへ）
            else:
                break  # 他のモード選択後はメニューから抜ける
        elif settings.get_mode() == "average" and choice == len(mode_options):  # weights設定
            if _show_weights_submenu(settings):
                break  # 重み設定完了した場合はメニューから抜ける
            # Falseの場合はトップメニューに戻る（continueで次のループへ）


def _show_weights_submenu(settings: SearchModeSettings):
    """重み設定サブメニューを表示"""
    console = Console()
    
    while True:
        console.print(f"\n[bold]=== 重み設定 (averageモード) ===[/bold]")
        current_weights = settings.weights
        console.print(f"現在の重み: content={current_weights[0]:.2f}, reasoning={current_weights[1]:.2f}, summary={current_weights[2]:.2f}")
        
        # プリセット選択肢
        preset_options = [
            ([1.0, 1.0, 1.0], "均等重み (デフォルト)"),
            ([0.7, 0.2, 0.1], "content重視"),
            ([0.2, 0.7, 0.1], "reasoning重視"),
            ([0.1, 0.2, 0.7], "summary重視"),
            ([0.5, 0.5, 0.0], "content + reasoning"),
            ([0.5, 0.0, 0.5], "content + summary"),
            ([0.0, 0.5, 0.5], "reasoning + summary")
        ]
        
        menu_items = []
        for i, (weights, description) in enumerate(preset_options, 1):
            _add_menu_option(menu_items, i, weights == current_weights, description)
        
        _add_menu_option(menu_items, len(preset_options)+1, False, "カスタム重み入力")
        _add_menu_option(menu_items, 0, False, "戻る")
        
        terminal_menu = TerminalMenu(menu_items, title="重み設定を選択してください:", show_search_hint=True)
        choice = terminal_menu.show()
        
        if choice is None or choice == len(menu_items) - 1:  # ESCまたは戻る
            return False  # トップメニューに戻る
        elif choice < len(preset_options):  # プリセット選択
            weights, description = preset_options[choice]
            settings.set_weights(weights)
            console.print(f"[green]重みを設定しました: {description}[/green]")
            return True  # 設定完了してメニューから抜ける
        elif choice == len(preset_options):  # カスタム入力
            if _handle_custom_weights(settings):
                return True  # 設定完了してメニューから抜ける


def _handle_custom_weights(settings: SearchModeSettings):
    """カスタム重み入力の処理"""
    console = Console()
    console.print("\n[bold]カスタム重み入力[/bold]")
    console.print("3つの値をスペース区切りで入力してください (例: 0.7 0.2 0.1)")
    console.print("合計値は自動で正規化されます")
    
    weights_input = safe_text_input("重み (content reasoning summary): ", "weights_input")
    
    if weights_input is None:  # Ctrl+D
        return False
    elif weights_input == "":  # 空入力はキャンセル
        return False
    
    try:
        # スペース区切りで分割して数値に変換
        weights_str = weights_input.strip().split()
        if len(weights_str) != 3:
            console.print("[red]エラー: 3つの値を入力してください[/red]")
            return False
        
        weights = [float(w) for w in weights_str]
        
        # 負の値チェック
        if any(w < 0 for w in weights):
            console.print("[red]エラー: 重みは0以上の値にしてください[/red]")
            return False
        
        # 全て0チェック
        if sum(weights) == 0:
            console.print("[red]エラー: すべての重みが0です[/red]")
            return False
        
        settings.set_weights(weights)
        console.print(f"[green]カスタム重みを設定しました[/green]")
        return True  # 設定完了
        
    except ValueError:
        console.print("[red]エラー: 数値を入力してください[/red]")
        return False


def show_view_mode_menu(settings: ViewModeSettings):
    """表示モード設定メニューを表示"""
    console = Console()
    
    # 表示モード選択肢
    view_mode_options = [
        ("normal", "通常モード（Panel表示、top_k件）"),
        ("list", "一覧モード（1行1情報、100件固定）"),
        ("detail", "詳細モード（Panel内にcontent/summary/reasoning分離）")
    ]
    
    console.print(f"\n[bold]=== 表示モード設定 ===[/bold]")
    console.print(f"現在の設定: {settings.format_status()}")
    
    # メニューオプション作成
    menu_items = []
    for i, (mode, description) in enumerate(view_mode_options, 1):
        if mode == settings.get_view_mode():
            menu_items.append(f"[{i}] ● {description}")
        else:
            menu_items.append(f"[{i}] {description}")
    
    menu_items.append(f"[0] 戻る")
    
    terminal_menu = TerminalMenu(menu_items, title="表示モードを選択してください:", show_search_hint=True)
    choice = terminal_menu.show()
    
    if choice is None:  # ESCキー
        return
    elif choice == len(menu_items) - 1:  # [0] 戻る
        return
    elif choice < len(view_mode_options):  # モード選択
        mode, description = view_mode_options[choice]
        settings.set_view_mode(mode)
        console.print(f"[green]表示モードを '{settings.format_status()}' に設定しました[/green]")