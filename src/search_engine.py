#!/usr/bin/env python3
"""
Twilogベクトル検索エンジン
"""
from typing import List, Tuple, Generator
from settings import UserFilterSettings, DateFilterSettings, TopKSettings
from data_csv import TwilogDataAccess


class SearchEngine:
    """Twilogベクトル検索クラス"""
    
    def __init__(self, csv_path: str):
        """
        初期化
        
        Args:
            csv_path: データベースファイルのパス
        """
        # データアクセス層の初期化
        self.data_access = TwilogDataAccess(csv_path)
        
        # ユーザーフィルタリング設定
        self.user_filter_settings = UserFilterSettings({})
        
        # 日付フィルタリング設定
        self.date_filter_settings = DateFilterSettings()
        
        # 表示件数設定
        self.top_k_settings = TopKSettings(10)
        
        # ユーザー情報の読み込み
        self.post_user_map, self.user_post_counts = self.data_access.load_user_data()
        
        # 設定クラスにユーザー情報を設定
        self.user_filter_settings = UserFilterSettings(self.user_post_counts)
    
    def search(self, vector_search_results: List[Tuple[int, float]]) -> Generator[Tuple[int, float, dict], None, None]:
        """
        ベクトル検索の結果を絞り込む
        
        Args:
            query: 検索クエリ
            
        Yields:
            (rank, similarity, post_info)のタプル
        """
        # 重複除去用の辞書
        seen_combinations = {}  # (user, content) -> (post_id, similarity, timestamp, url)
        
        rank = 1
        for post_id, similarity in vector_search_results:
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
                _, _, existing_timestamp, _ = seen_combinations[key]
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