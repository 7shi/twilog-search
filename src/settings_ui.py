#!/usr/bin/env python3
"""
設定UI機能を提供するモジュール
"""

from rich.console import Console
from simple_term_menu import TerminalMenu
from safe_input import safe_text_input, safe_number_input, safe_date_input, yes_no_menu
from settings import UserFilterSettings, DateFilterSettings, TopKSettings


def show_user_filter_menu(settings: UserFilterSettings):
    """ユーザーフィルタリングメニューを表示"""
    while True:
        print(f"\n=== ユーザーフィルタリング設定 ===")
        print(f"現在の設定: {settings.format_status()}")
        
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
            settings.set_none()
            print("フィルタリングを無効にしました")
            return  # noneは即座に抜ける
            
        elif choice_index == 1:  # includes
            _handle_includes(settings)
            
        elif choice_index == 2:  # excludes
            _handle_excludes(settings)
            
        elif choice_index == 3:  # threshold min
            _handle_threshold_min(settings)
            
        elif choice_index == 4:  # threshold max
            _handle_threshold_max(settings)


def _handle_includes(settings: UserFilterSettings):
    """includes設定の処理"""
    users_input = safe_text_input(
        "ユーザー名をコンマ区切りで入力: ",
        history="user"
    )
    
    if users_input is None:
        # Ctrl+Dの場合、何も変更せずにメニューに戻る
        return
    elif users_input.strip():
        users = [user.strip() for user in users_input.split(',') if user.strip()]
        # includes設定時は他の設定をすべてクリア
        settings.set_includes(users)
        console = Console()
        console.print(f"[green]includes設定: {len(users)}人のユーザーを対象[/green]")
        return  # includesは即座に抜ける
    else:
        # 無入力の場合、値を消去するか確認
        if settings.has_includes():
            current_value = settings.get_includes()
            should_clear = yes_no_menu(
                f"現在のincludes設定({len(current_value)}人)を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_includes()
                console.print(f"[green]includes設定を消去しました[/green]")
                console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
        # 回答に関わらずメニューに戻る
        return


def _handle_excludes(settings: UserFilterSettings):
    """excludes設定の処理"""
    users_input = safe_text_input(
        "除外ユーザー名をコンマ区切りで入力: ",
        history="user"
    )
    
    if users_input is None:
        # Ctrl+Dの場合、何も変更せずにメニューに戻る
        return
    elif users_input.strip():
        users = [user.strip() for user in users_input.split(',') if user.strip()]
        # excludes設定時は他の設定をすべてクリア
        settings.set_excludes(users)
        console = Console()
        console.print(f"[green]excludes設定: {len(users)}人のユーザーを除外[/green]")
        return  # excludesは即座に抜ける
    else:
        # 無入力の場合、値を消去するか確認
        if settings.has_excludes():
            current_value = settings.get_excludes()
            should_clear = yes_no_menu(
                f"現在のexcludes設定({len(current_value)}人)を消去しますか？",
                default_yes=False
            )
            if should_clear:
                console = Console()
                settings.clear_excludes()
                console.print(f"[green]excludes設定を消去しました[/green]")
                console.print(f"[dim]現在の設定: {settings.format_status()}[/dim]")
        # 回答に関わらずメニューに戻る
        return


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