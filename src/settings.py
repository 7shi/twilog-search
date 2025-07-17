#!/usr/bin/env python3
"""
設定情報を格納するデータクラス
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

DEFAULT_MODE = "content"
DEFAULT_VIEW_MODE = "normal"


class UserFilterSettings:
    """ユーザーフィルタリング設定クラス"""
    
    def __init__(self):
        """初期化"""
        self.filter_settings = {}
    
    def set_none(self):
        """フィルタリングを無効化"""
        self.filter_settings = {}
    
    def set_includes(self, users: List[str]):
        """指定ユーザーのみを対象とする設定"""
        self.filter_settings = {"includes": users}
    
    def set_excludes(self, users: List[str]):
        """指定ユーザーを除外する設定"""
        self.filter_settings = {"excludes": users}
    
    def set_threshold_min(self, min_posts: int):
        """投稿数下限を設定（上限が矛盾する場合は削除）"""
        new_filter = {"threshold_min": min_posts}
        if "threshold_max" in self.filter_settings:
            max_posts = self.filter_settings["threshold_max"]
            if min_posts < max_posts:
                new_filter["threshold_max"] = max_posts
        self.filter_settings = new_filter
    
    def set_threshold_max(self, max_posts: int):
        """投稿数上限を設定（下限が矛盾する場合は削除）"""
        new_filter = {"threshold_max": max_posts}
        if "threshold_min" in self.filter_settings:
            min_posts = self.filter_settings["threshold_min"]
            if min_posts < max_posts:
                new_filter["threshold_min"] = min_posts
        self.filter_settings = new_filter
    
    def clear_includes(self):
        """includes設定を削除"""
        if "includes" in self.filter_settings:
            del self.filter_settings["includes"]
    
    def clear_excludes(self):
        """excludes設定を削除"""
        if "excludes" in self.filter_settings:
            del self.filter_settings["excludes"]
    
    def clear_threshold_min(self):
        """threshold min設定を削除"""
        if "threshold_min" in self.filter_settings:
            del self.filter_settings["threshold_min"]
    
    def clear_threshold_max(self):
        """threshold max設定を削除"""
        if "threshold_max" in self.filter_settings:
            del self.filter_settings["threshold_max"]
    
    def has_includes(self) -> bool:
        """includes設定があるかチェック"""
        return "includes" in self.filter_settings
    
    def has_excludes(self) -> bool:
        """excludes設定があるかチェック"""
        return "excludes" in self.filter_settings
    
    def has_threshold_min(self) -> bool:
        """threshold min設定があるかチェック"""
        return "threshold_min" in self.filter_settings
    
    def has_threshold_max(self) -> bool:
        """threshold max設定があるかチェック"""
        return "threshold_max" in self.filter_settings
    
    def get_includes(self) -> Optional[List[str]]:
        """includes設定を取得"""
        return self.filter_settings.get("includes")
    
    def get_excludes(self) -> Optional[List[str]]:
        """excludes設定を取得"""
        return self.filter_settings.get("excludes")
    
    def get_threshold_min(self) -> Optional[int]:
        """threshold min設定を取得"""
        return self.filter_settings.get("threshold_min")
    
    def get_threshold_max(self) -> Optional[int]:
        """threshold max設定を取得"""
        return self.filter_settings.get("threshold_max")
    
    def format_status(self) -> str:
        """フィルタリング状態を文字列でフォーマット"""
        if not self.filter_settings:
            return "すべてのユーザー"
        
        status_parts = []
        
        # includes/excludesは排他的
        if "includes" in self.filter_settings:
            users = self.filter_settings['includes']
            if len(users) <= 3:
                user_list = ", ".join(users)
                status_parts.append(f"includes: {user_list}")
            else:
                user_list = ", ".join(users[:3])
                status_parts.append(f"includes: {user_list}...({len(users)}人)")
        elif "excludes" in self.filter_settings:
            users = self.filter_settings['excludes']
            if len(users) <= 3:
                user_list = ", ".join(users)
                status_parts.append(f"excludes: {user_list}")
            else:
                user_list = ", ".join(users[:3])
                status_parts.append(f"excludes: {user_list}...({len(users)}人)")
        
        # threshold系は組み合わせ可能
        if "threshold_min" in self.filter_settings:
            status_parts.append(f"min={self.filter_settings['threshold_min']}")
        if "threshold_max" in self.filter_settings:
            status_parts.append(f"max={self.filter_settings['threshold_max']}")
        
        return " + ".join(status_parts) if status_parts else "unknown"
    
    def is_user_allowed(self, user: str, user_post_counts: Dict[str, int]) -> bool:
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
        post_count = user_post_counts.get(user, 0)
        
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
    
    def set_all(self):
        """フィルタリングを無効化"""
        self.filter_settings = {}
    
    def set_from(self, from_date: str):
        """開始日時を設定（終了日時が矛盾する場合は削除）"""
        new_filter = {"from": from_date}
        if "to" in self.filter_settings:
            to_date = self.filter_settings["to"]
            if from_date < to_date:
                new_filter["to"] = to_date
        self.filter_settings = new_filter
    
    def set_to(self, to_date: str):
        """終了日時を設定（開始日時が矛盾する場合は削除）"""
        new_filter = {"to": to_date}
        if "from" in self.filter_settings:
            from_date = self.filter_settings["from"]
            if from_date < to_date:
                new_filter["from"] = from_date
        self.filter_settings = new_filter
    
    def clear_from(self):
        """from設定を削除"""
        if "from" in self.filter_settings:
            del self.filter_settings["from"]
    
    def clear_to(self):
        """to設定を削除"""
        if "to" in self.filter_settings:
            del self.filter_settings["to"]
    
    def has_from(self) -> bool:
        """from設定があるかチェック"""
        return "from" in self.filter_settings
    
    def has_to(self) -> bool:
        """to設定があるかチェック"""
        return "to" in self.filter_settings
    
    def get_from(self) -> Optional[str]:
        """from設定を取得"""
        return self.filter_settings.get("from")
    
    def get_to(self) -> Optional[str]:
        """to設定を取得"""
        return self.filter_settings.get("to")
    
    def format_status(self) -> str:
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
    
    def set_top_k(self, top_k: int):
        """表示件数を設定"""
        self.top_k = top_k
    
    def get_top_k(self) -> int:
        """表示件数を取得"""
        return self.top_k


class SearchModeSettings:
    """検索モード設定クラス"""
    
    def __init__(self, mode: str = DEFAULT_MODE, weights: Optional[List[float]] = None):
        """
        初期化
        
        Args:
            mode: 検索モード
            weights: averageモード用の重み（デフォルト: [1.0, 1.0, 1.0]）
        """
        self.mode = mode
        self.weights = weights or [1.0, 1.0, 1.0]
    
    def set_mode(self, mode: str):
        """検索モードを設定"""
        self.mode = mode
        # averageモード以外では重みをクリア
        if mode != "average":
            self.weights = [1.0, 1.0, 1.0]
    
    def set_weights(self, weights: List[float]):
        """重みを設定（averageモード時のみ有効）"""
        if self.mode == "average":
            # 重みを正規化
            weight_sum = sum(weights)
            if weight_sum > 0:
                self.weights = [w / weight_sum for w in weights]
            else:
                self.weights = [1.0, 1.0, 1.0]
        else:
            self.weights = [1.0, 1.0, 1.0]
    
    def get_mode(self) -> str:
        """検索モードを取得"""
        return self.mode
    
    def get_weights(self) -> Optional[List[float]]:
        """重みを取得（averageモード時のみ）"""
        if self.mode == "average" and self.weights != [1.0, 1.0, 1.0]:
            return self.weights
        return None
    
    def format_status(self) -> str:
        """モード設定状態を文字列でフォーマット"""
        if self.mode == "average" and self.weights != [1.0, 1.0, 1.0]:
            weights_str = ", ".join(f"{w:.2f}" for w in self.weights)
            return f"{self.mode} (weights: {weights_str})"
        return self.mode


class ViewModeSettings:
    """表示モード設定クラス"""
    
    def __init__(self, view_mode: str = DEFAULT_VIEW_MODE):
        """
        初期化
        
        Args:
            view_mode: 表示モード（normal, list, detail）
        """
        self.view_mode = view_mode
    
    def set_view_mode(self, view_mode: str):
        """表示モードを設定"""
        if view_mode in ["normal", "list", "detail"]:
            self.view_mode = view_mode
        else:
            raise ValueError(f"無効な表示モード: {view_mode}")
    
    def get_view_mode(self) -> str:
        """表示モードを取得"""
        return self.view_mode
    
    def format_status(self) -> str:
        """表示モード設定状態を文字列でフォーマット"""
        mode_names = {
            "normal": "通常",
            "list": "一覧", 
            "detail": "詳細"
        }
        return mode_names.get(self.view_mode, self.view_mode)


class SearchSettings:
    """検索設定を統合管理するクラス"""
    
    def __init__(self, initial_top_k: int = 10):
        """
        初期化
        
        Args:
            initial_top_k: 初期表示件数
        """
        self.user_filter = UserFilterSettings()
        self.date_filter = DateFilterSettings()
        self.top_k = TopKSettings(initial_top_k)
        self.mode_settings = SearchModeSettings()
        self.view_mode = ViewModeSettings()
    
    def to_dict(self) -> Dict[str, Any]:
        """設定をDict形式にシリアライズ"""
        return {
            "user_filter": self.user_filter.filter_settings,
            "date_filter": self.date_filter.filter_settings,
            "top_k": self.top_k.get_top_k()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchSettings':
        """Dict形式から設定をデシリアライズ"""
        initial_top_k = data.get("top_k", 10)
        
        # インスタンス作成
        settings = cls(initial_top_k)
        
        # user_filterの設定を復元
        if "user_filter" in data:
            settings.user_filter.filter_settings = data["user_filter"]
        
        # date_filterの設定を復元
        if "date_filter" in data:
            settings.date_filter.filter_settings = data["date_filter"]
        
        # mode_settingsの設定を復元
        if "mode_settings" in data:
            mode_data = data["mode_settings"]
            settings.mode_settings = SearchModeSettings(
                mode=mode_data.get("mode", DEFAULT_MODE),
                weights=mode_data.get("weights", [1.0, 1.0, 1.0])
            )
        
        return settings
    
