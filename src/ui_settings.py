#!/usr/bin/env python3
"""
設定UI機能を提供するモジュール
"""

from datetime import datetime
from rich.console import Console
from simple_term_menu import TerminalMenu
from safe_input import safe_text_input, safe_number_input, safe_date_input, yes_no_menu


class UserFilterSettings:
    """ユーザーフィルタリング設定クラス"""
    
    def __init__(self, user_post_counts):
        """
        初期化
        
        Args:
            user_post_counts: ユーザーごとの投稿数辞書
        """
        self.user_post_counts = user_post_counts
        self.filter_settings = {}
    
    def show_menu(self):
        """ユーザーフィルタリングメニューを表示"""
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
                self.filter_settings = {}
                print("フィルタリングを無効にしました")
                return  # noneは即座に抜ける
                
            elif choice_index == 1:  # includes
                self._handle_includes()
                
            elif choice_index == 2:  # excludes
                self._handle_excludes()
                
            elif choice_index == 3:  # threshold min
                self._handle_threshold_min()
                
            elif choice_index == 4:  # threshold max
                self._handle_threshold_max()
    
    def _handle_includes(self):
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
            self.filter_settings = {"includes": users}
            console = Console()
            console.print(f"[green]includes設定: {len(users)}人のユーザーを対象[/green]")
            return  # includesは即座に抜ける
        else:
            # 無入力の場合、値を消去するか確認
            current_value = self.filter_settings.get("includes", None)
            if current_value is not None:
                should_clear = yes_no_menu(
                    f"現在のincludes設定({len(current_value)}人)を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["includes"]
                    console.print(f"[green]includes設定を消去しました[/green]")
                    console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
            # 回答に関わらずメニューに戻る
            return
    
    def _handle_excludes(self):
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
            self.filter_settings = {"excludes": users}
            console = Console()
            console.print(f"[green]excludes設定: {len(users)}人のユーザーを除外[/green]")
            return  # excludesは即座に抜ける
        else:
            # 無入力の場合、値を消去するか確認
            current_value = self.filter_settings.get("excludes", None)
            if current_value is not None:
                should_clear = yes_no_menu(
                    f"現在のexcludes設定({len(current_value)}人)を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["excludes"]
                    console.print(f"[green]excludes設定を消去しました[/green]")
                    console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
            # 回答に関わらずメニューに戻る
            return
    
    def _handle_threshold_min(self):
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
            current_value = self.filter_settings.get("threshold_min", None)
            if current_value is not None:
                should_clear = yes_no_menu(
                    f"現在のthreshold min設定({current_value})を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["threshold_min"]
                    console.print(f"[green]threshold min設定を消去しました[/green]")
                    console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
            # 回答に関わらずメニューに戻る
            return
        
        # 上限との整合性チェック
        console = Console()
        if "threshold_max" in self.filter_settings:
            max_posts = self.filter_settings["threshold_max"]
            if min_posts >= max_posts:
                console.print(f"[yellow]threshold max設定({max_posts})がthreshold min設定({min_posts})と矛盾するため削除しました[/yellow]")
        
        # includes/excludesを削除し、threshold系のみ保持
        new_filter = {"threshold_min": min_posts}
        if "threshold_max" in self.filter_settings:
            max_posts = self.filter_settings["threshold_max"]
            if min_posts < max_posts:
                new_filter["threshold_max"] = max_posts
        self.filter_settings = new_filter
            
        console.print(f"[green]threshold min={min_posts}: 投稿数{min_posts}以上のユーザーを対象[/green]")
        console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
        # threshold minはメニューに戻る（continueで次のループへ）
    
    def _handle_threshold_max(self):
        """threshold max設定の処理"""
        # 下限が設定されている場合は、それより大きい値を要求
        min_threshold = None
        if "threshold_min" in self.filter_settings:
            min_threshold = self.filter_settings["threshold_min"] + 1
        
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
            current_value = self.filter_settings.get("threshold_max", None)
            if current_value is not None:
                should_clear = yes_no_menu(
                    f"現在のthreshold max設定({current_value})を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["threshold_max"]
                    console.print(f"[green]threshold max設定を消去しました[/green]")
                    console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
            # 回答に関わらずメニューに戻る
            return
        
        # 下限との整合性チェック
        console = Console()
        if "threshold_min" in self.filter_settings:
            min_posts = self.filter_settings["threshold_min"]
            if max_posts <= min_posts:
                console.print(f"[yellow]threshold min設定({min_posts})がthreshold max設定({max_posts})と矛盾するため削除しました[/yellow]")
        
        # includes/excludesを削除し、threshold系のみ保持
        new_filter = {"threshold_max": max_posts}
        if "threshold_min" in self.filter_settings:
            min_posts = self.filter_settings["threshold_min"]
            if min_posts < max_posts:
                new_filter["threshold_min"] = min_posts
        self.filter_settings = new_filter
            
        console.print(f"[green]threshold max={max_posts}: 投稿数{max_posts}以下のユーザーを対象[/green]")
        console.print(f"[dim]現在の設定: {self._format_filter_status()}[/dim]")
        # threshold maxはメニューに戻る（continueで次のループへ）
    
    def _format_filter_status(self) -> str:
        """フィルタリング状態を文字列でフォーマット"""
        if not self.filter_settings:
            return "すべてのユーザー"
        
        status_parts = []
        
        # includes/excludesは排他的
        if "includes" in self.filter_settings:
            status_parts.append(f"includes ({len(self.filter_settings['includes'])}人)")
        elif "excludes" in self.filter_settings:
            status_parts.append(f"excludes ({len(self.filter_settings['excludes'])}人)")
        
        # threshold系は組み合わせ可能
        if "threshold_min" in self.filter_settings:
            status_parts.append(f"min={self.filter_settings['threshold_min']}")
        if "threshold_max" in self.filter_settings:
            status_parts.append(f"max={self.filter_settings['threshold_max']}")
        
        return " + ".join(status_parts) if status_parts else "unknown"
    
    def is_user_allowed(self, user: str) -> bool:
        """ユーザーがフィルタリング条件を満たすかチェック"""
        if not self.filter_settings:
            return True
        
        # includes/excludesのチェック（排他的）
        if "includes" in self.filter_settings:
            if user not in self.filter_settings["includes"]:
                return False
        elif "excludes" in self.filter_settings:
            if user in self.filter_settings["excludes"]:
                return False
        
        # threshold系のチェック（組み合わせ可能）
        post_count = self.user_post_counts.get(user, 0)
        
        if "threshold_min" in self.filter_settings:
            if post_count < self.filter_settings["threshold_min"]:
                return False
                
        if "threshold_max" in self.filter_settings:
            if post_count > self.filter_settings["threshold_max"]:
                return False
        
        return True


class DateFilterSettings:
    """日付フィルタリング設定クラス"""
    
    def __init__(self):
        """初期化"""
        self.filter_settings = {}
    
    def show_menu(self):
        """日付フィルタリングメニューを表示"""
        print(f"\n=== 日付フィルタリング設定 ===")
        
        while True:
            print(f"現在の設定: {self._format_filter_status()}")
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
                self.filter_settings = {}
                print("日付フィルタリングを無効にしました")
                return  # allは即座に抜ける
                
            elif choice_index == 1:  # from
                self._handle_from_date()
                
            elif choice_index == 2:  # to
                self._handle_to_date()
    
    def _handle_from_date(self):
        """from日付設定の処理"""
        from_date = safe_date_input("開始日時を入力: ", "date_input")
        
        if from_date is None:
            return  # Ctrl+Dの場合はメニューに戻る
        elif from_date == "":
            # 無入力の場合、値を消去するか確認
            if "from" in self.filter_settings:
                current_value = self.filter_settings["from"][:10]
                should_clear = yes_no_menu(
                    f"現在のfrom設定({current_value})を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["from"]
                    console.print(f"[green]from設定を消去しました[/green]")
        else:
            # 適切な日付が入力された場合の処理
            console = Console()
            # toは引き継ぐが、他の設定はクリア
            new_filter = {"from": from_date}
            if "to" in self.filter_settings:
                to_date = self.filter_settings["to"]
                if from_date < to_date:
                    new_filter["to"] = to_date
                else:
                    console.print(f"[yellow]to設定({to_date[:10]})がfrom設定({from_date[:10]})と矛盾するため削除しました[/yellow]")
            self.filter_settings = new_filter
            console.print(f"[green]from設定: {from_date}以降の投稿を対象[/green]")
        # from設定後はメニューに戻る
    
    def _handle_to_date(self):
        """to日付設定の処理"""
        to_date = safe_date_input("終了日時を入力: ", "date_input")
        
        if to_date is None:
            return  # Ctrl+Dの場合はメニューに戻る
        elif to_date == "":
            # 無入力の場合、値を消去するか確認
            if "to" in self.filter_settings:
                current_value = self.filter_settings["to"][:10]
                should_clear = yes_no_menu(
                    f"現在のto設定({current_value})を消去しますか？",
                    default_yes=False
                )
                if should_clear:
                    console = Console()
                    del self.filter_settings["to"]
                    console.print(f"[green]to設定を消去しました[/green]")
        else:
            # 適切な日付が入力された場合の処理
            console = Console()
            # fromは引き継ぐが、他の設定はクリア
            new_filter = {"to": to_date}
            if "from" in self.filter_settings:
                from_date = self.filter_settings["from"]
                if from_date < to_date:
                    new_filter["from"] = from_date
                else:
                    console.print(f"[yellow]from設定({from_date[:10]})がto設定({to_date[:10]})と矛盾するため削除しました[/yellow]")
            self.filter_settings = new_filter
            console.print(f"[green]to設定: {to_date}以前の投稿を対象[/green]")
        # to設定後はメニューに戻る
    
    def _format_filter_status(self) -> str:
        """日付フィルタリング状態を文字列でフォーマット"""
        if not self.filter_settings:
            return "すべての日付"
        elif "from" in self.filter_settings and "to" not in self.filter_settings:
            return f"from {self.filter_settings['from']}"
        elif "to" in self.filter_settings and "from" not in self.filter_settings:
            return f"to {self.filter_settings['to']}"
        elif "from" in self.filter_settings and "to" in self.filter_settings:
            return f"from {self.filter_settings['from']} to {self.filter_settings['to']}"
        return "unknown"
    
    def is_date_allowed(self, timestamp: str) -> bool:
        """投稿日時がフィルタリング条件を満たすかチェック"""
        if not self.filter_settings:
            return True
            
        if not timestamp:
            return True
            
        try:
            post_dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
            
            if "from" in self.filter_settings and "to" not in self.filter_settings:
                # from のみ指定
                from_dt = datetime.strptime(self.filter_settings["from"], '%Y-%m-%d %H:%M:%S')
                return post_dt >= from_dt
                
            elif "to" in self.filter_settings and "from" not in self.filter_settings:
                # to のみ指定
                to_dt = datetime.strptime(self.filter_settings["to"], '%Y-%m-%d %H:%M:%S')
                return post_dt <= to_dt
                
            elif "from" in self.filter_settings and "to" in self.filter_settings:
                # from-to 両方指定
                from_dt = datetime.strptime(self.filter_settings["from"], '%Y-%m-%d %H:%M:%S')
                to_dt = datetime.strptime(self.filter_settings["to"], '%Y-%m-%d %H:%M:%S')
                return from_dt <= post_dt <= to_dt
                
        except (ValueError, TypeError):
            return True
            
        return True


class TopKSettings:
    """表示件数設定クラス"""
    
    def __init__(self, initial_top_k: int = 10):
        """
        初期化
        
        Args:
            initial_top_k: 初期表示件数
        """
        self.top_k = initial_top_k
    
    def show_menu(self):
        """表示件数設定メニューを表示"""
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
        
        if new_top_k:
            self.top_k = new_top_k
            console.print(f"[green]表示件数を{new_top_k}件に設定しました[/green]")
