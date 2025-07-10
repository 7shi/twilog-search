#!/usr/bin/env python3
"""
TwilogCSVデータアクセス機能
"""
import csv
import html
import re
from typing import Dict, List, Tuple, Optional


def strip_content(text: str) -> str:
    """
    テキストからメンション・URLを除去する（ハッシュタグ保持）
    
    Args:
        text: 処理対象のテキスト
        
    Returns:
        処理されたテキスト
    """
    if not text:
        return ""
    
    # URLを除去（ASCII文字のみ許可）
    url_pattern = r'https?://[a-zA-Z0-9._~:/?#[\]@!$&\'()*+,;=%-]+'
    text = re.sub(url_pattern, '', text)
    
    # メンションを除去（@ユーザー名）
    mention_pattern = r'@[a-zA-Z0-9_]+'
    text = re.sub(mention_pattern, '', text)
    
    # 余分な空白を除去
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def extract_urls(text: str) -> List[str]:
    """
    テキストからURLを抽出する
    
    Args:
        text: 抽出対象のテキスト
        
    Returns:
        抽出されたURLのリスト
    """
    if not text:
        return []
    
    # URLを抽出（ASCII文字のみ許可）
    url_pattern = r'https?://[a-zA-Z0-9._~:/?#[\]@!$&\'()*+,;=%-]+'
    urls = re.findall(url_pattern, text)
    
    return urls


class TwilogDataAccess:
    """TwilogCSVファイルへのアクセスを管理するクラス"""
    
    def __init__(self, csv_path: str = "twilog.csv"):
        """
        初期化
        
        Args:
            csv_path: メインCSVファイルのパス
        """
        self.csv_path = csv_path
        
        # データをメモリに読み込み
        print("CSVデータを読み込み中...")
        self._load_csv_data()
        self._extract_users_from_csv()
    
    def _load_csv_data(self):
        """メインCSVファイルを読み込む"""
        self.posts_data = {}
        
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            # CSVの構造: post_id, url, timestamp, content, log_type
            csv_reader = csv.reader(f)
            
            for row in csv_reader:
                if len(row) >= 5:
                    post_id = int(row[0].strip('"'))
                    url = row[1].strip('"')
                    timestamp = row[2].strip('"')
                    content = html.unescape(row[3].strip('"'))
                    log_type = row[4].strip('"')
                    
                    self.posts_data[post_id] = {
                        'url': url,
                        'timestamp': timestamp,
                        'content': content,
                        'log_type': log_type
                    }
    
    def _extract_user_and_post_id(self, url: str) -> Optional[Tuple[str, str]]:
        """
        TwitterのURLからユーザー名とpost_idを抽出する
        
        Args:
            url: Twitter/X.comのURL
        
        Returns:
            (user, post_id)のタプル、または抽出できない場合はNone
        """
        pattern = r'https?://(?:www\.)?(?:twitter\.com|x\.com)/([^/]+)/status/(\d+)'
        match = re.search(pattern, url)
        
        if match:
            user = match.group(1)
            post_id = match.group(2)
            return (user, post_id)
        
        return None
    
    def _extract_users_from_csv(self):
        """CSVファイルのURLからユーザー情報を抽出する"""
        self.post_user_map = {}
        self.user_post_counts = {}
        
        results = {}  # post_id -> (user, post_id, log_type)
        
        for post_id, post_data in self.posts_data.items():
            url = post_data['url']
            log_type = int(post_data['log_type'])
            
            if url:
                result = self._extract_user_and_post_id(url)
                if result:
                    user, extracted_post_id = result
                    
                    # post_idの一致を確認
                    if str(post_id) == extracted_post_id:
                        # 既存のpost_idがある場合、log_typeが大きい場合のみ上書き
                        if post_id in results:
                            existing_user, existing_post_id, existing_log_type = results[post_id]
                            if log_type > existing_log_type:
                                results[post_id] = (user, post_id, log_type)
                        else:
                            results[post_id] = (user, post_id, log_type)
        
        # post_user_mapとuser_post_countsを構築
        for user, post_id, log_type in results.values():
            self.post_user_map[post_id] = user
            self.user_post_counts[user] = self.user_post_counts.get(user, 0) + 1
    
    def load_user_data(self) -> Tuple[Dict[int, str], Dict[str, int]]:
        """
        ユーザー情報を読み込む
        
        Returns:
            (post_user_map, user_post_counts): 投稿ID→ユーザー名マップとユーザー別投稿数
        """
        return self.post_user_map, self.user_post_counts
    
    def get_post_content(self, post_ids: List[int]) -> Dict[int, Dict[str, str]]:
        """
        投稿IDから投稿内容を取得する
        
        Args:
            post_ids: 投稿IDのリスト
            
        Returns:
            投稿ID→投稿情報の辞書
        """
        if not post_ids:
            return {}
        
        result = {}
        for post_id in post_ids:
            if post_id in self.posts_data:
                post_data = self.posts_data[post_id]
                user = self.post_user_map.get(post_id, None)
                
                result[post_id] = {
                    'content': post_data['content'],
                    'timestamp': post_data['timestamp'],
                    'url': post_data['url'],
                    'user': user
                }
        
        return result
