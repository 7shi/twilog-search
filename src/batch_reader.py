#!/usr/bin/env python3
"""
バッチ処理結果読み込みモジュール
"""
from typing import Dict, Optional
from pathlib import Path
import json


class BatchReader:
    """batch/results.jsonlファイルの読み込みクラス"""
    
    def __init__(self, jsonl_path: Path):
        """
        初期化
        
        Args:
            jsonl_path: batch/results.jsonlファイルのパス
        """
        self.jsonl_path = jsonl_path
        self.summaries_data: Dict[int, dict] = {}
        self.tag_index: Dict[str, list] = {}
        self.initialized = False
    
    def initialize(self) -> None:
        """遅延初期化を実行"""
        if self.initialized:
            return
        
        self.load_summaries_data()
        self.build_tag_index()
        self.initialized = True
    
    def load_summaries_data(self) -> None:
        """
        batch/results.jsonlを読み込んでサマリデータをフィールドに保存
        """
        self.summaries_data = {}
        
        if not self.jsonl_path.exists():
            return
        
        try:
            with open(self.jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    data = json.loads(line)
                    post_id = data["key"]
                    self.summaries_data[post_id] = {
                        "reasoning": data["reasoning"],
                        "summary": data["summary"],
                        "tags": data["tags"]
                    }
        except (json.JSONDecodeError, KeyError) as e:
            # タグデータの読み込みに失敗した場合は空のディクショナリを保持
            self.summaries_data = {}
    
    def build_tag_index(self) -> None:
        """
        タグから投稿IDへの逆引きインデックスを構築してフィールドに保存
        """
        self.tag_index = {}
        
        for post_id, summary_data in self.summaries_data.items():
            tags = summary_data.get("tags", [])
            for tag in tags:
                if tag not in self.tag_index:
                    self.tag_index[tag] = []
                self.tag_index[tag].append(post_id)