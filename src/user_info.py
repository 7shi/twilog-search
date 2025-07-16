#!/usr/bin/env python3
"""
ユーザー情報管理クラス
"""

class UserInfo:
    """ユーザー情報管理クラス"""
    
    def __init__(self, user_list=None):
        """
        コンストラクタ
        
        Args:
            user_list: ユーザー名のリスト
        """
        self.user_list = user_list or []
        self._cached_matches = {}
    
    def user_completer(self, text, state):
        """ユーザー名補完関数"""
        # キャッシュから取得
        if text in self._cached_matches:
            matches = self._cached_matches[text]
        else:
            # 入力テキストに基づいて候補を絞り込み
            matches = [user for user in self.user_list if user.startswith(text)]
            # キャッシュに保存
            self._cached_matches[text] = matches
        
        # state番目の候補を返す
        if state < len(matches):
            return matches[state]
        else:
            return None
    
    def clear_cache(self):
        """キャッシュをクリア"""
        self._cached_matches.clear()
    
    def update_user_list(self, user_list):
        """ユーザーリストを更新"""
        self.user_list = user_list or []
        self.clear_cache()
    
    def suggest_users(self, user_list):
        """
        ユーザーのリストを受け取って存在しないユーザーに対してレーベンシュタイン距離で類似ユーザーを提案
        
        Args:
            user_list: チェック対象のユーザー名リスト
            
        Returns:
            存在しないユーザー名をキーとし、類似ユーザー上位5人をリストとする辞書
        """
        import Levenshtein
        
        # 存在しないユーザーを特定
        missing_users = [user for user in user_list if user not in self.user_list]
        
        result = {}
        
        for missing_user in missing_users:
            # 全ユーザーとのレーベンシュタイン類似度を計算
            similarities = []
            for existing_user in self.user_list:
                ratio = Levenshtein.ratio(missing_user, existing_user)
                similarities.append((existing_user, ratio))
            
            # 類似度の降順でソート
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # 上位5人を抽出
            top_5 = [user for user, _ in similarities[:5]]
            result[missing_user] = top_5
        
        return result