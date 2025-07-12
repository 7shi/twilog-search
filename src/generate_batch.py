#!/usr/bin/env python3
"""
CSVファイルのデータからバッチAPIリクエスト用のJSONLファイルを生成するスクリプト
"""

import argparse
import json
from pathlib import Path
from data_csv import TwilogDataAccess, strip_content

# TweetTagAnalysisSchemaをGeminiバッチAPI用のJSONスキーマに変換
schema = {
    "type": "OBJECT",
    "properties": {
        "reasoning": {
            "type": "STRING"
        },
        "summary": {
            "type": "STRING"
        },
        "tags": {
            "type": "ARRAY",
            "items": {
                "type": "STRING"
            }
        }
    },
    "required": ["reasoning", "summary", "tags"],
    "propertyOrdering": ["reasoning", "summary", "tags"]
}

# add_tags.pyのPROMPTを流用（分析項目をハードコーディング）
PROMPT = """下記のツイート内容を分析し、情報を抽出してください。

### 分析項目
- reasoning: 内容についての検討（日本語）
- summary: 簡潔な一行要約（日本語、30文字以内）
- tags: 投稿内容を表すタグのリスト（例：プログラミング、機械学習、日常、思考、技術解説）

### 指示
- 日本語で分析結果を記述してください
- 情報が明記されていない場合は推測せず、適切なデフォルト値を使用してください
- タグが不明な場合は空のリストを返してください
- タグは投稿の主要なトピックや分野を表すものにしてください""".strip()

def load_data_from_csv(csv_path):
    """
    CSVファイルからデータを読み込む
    
    Args:
        csv_path: CSVファイルのパス
        
    Returns:
        (post_id, content)のリスト
    """
    data_access = TwilogDataAccess(csv_path)
    
    data = []
    for post_id, post_data in data_access.posts_data.items():
        content = strip_content(post_data['content'])
        if content:  # 空でない場合のみ追加
            data.append((post_id, content))
    return data

def generate_batch_request(post_id, content):
    """
    1件のツイートデータからバッチAPIリクエストを生成する
    
    Args:
        post_id: 投稿ID
        content: ツイート内容
        
    Returns:
        バッチAPIリクエスト辞書
    """
    content_part = f"### ツイート内容\n{content}".rstrip()
    
    return {
        "key": str(post_id),
        "request": {
            "contents": [
                {
                    "parts": [
                        {"text": PROMPT},
                        {"text": content_part}
                    ]
                }
            ],
            "generation_config": {
                "response_mime_type": "application/json",
                "response_schema": schema
            }
        }
    }

def generate_batch_jsonl(csv_path, output_dir="batch", chunk_size=10000, limit=None):
    """
    CSVファイルからバッチAPIリクエスト用のJSONLファイルを生成する
    
    Args:
        csv_path: CSVファイルのパス
        output_dir: 出力ディレクトリ
        chunk_size: チャンクサイズ（デフォルト: 10000）
        limit: 生成件数の上限
    """
    # 出力ディレクトリ作成
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # データ読み込み
    data = load_data_from_csv(csv_path)
    
    if not data:
        print("処理対象のデータが見つかりませんでした")
        return
    
    # post_idでソート
    data.sort(key=lambda x: x[0])
    
    # limit制限の適用
    if limit is not None and len(data) > limit:
        data = data[:limit]
        print(f"limit制限により{limit}件に制限されました")
    
    total_files = (len(data) + chunk_size - 1) // chunk_size
    
    print(f"総データ数: {len(data)}件")
    print(f"チャンクサイズ: {chunk_size}件")
    print(f"生成ファイル数: {total_files}個")
    
    # チャンクごとにJSONLファイル生成
    for chunk_index in range(total_files):
        start_idx = chunk_index * chunk_size
        end_idx = min(start_idx + chunk_size, len(data))
        chunk_data = data[start_idx:end_idx]
        
        output_file = output_path / f"{chunk_index + 1:03d}.jsonl"
        
        with open(output_file, "w", encoding="utf-8") as f:
            for post_id, content in chunk_data:
                request = generate_batch_request(post_id, content)
                f.write(json.dumps(request, ensure_ascii=False) + "\n")
        
        print(f"生成完了: {output_file} ({len(chunk_data)}件)")
    
    print(f"\n全ファイル生成完了: {total_files}個のJSONLファイルを生成しました")

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="CSVファイルからバッチAPIリクエスト用のJSONLファイルを生成"
    )
    
    parser.add_argument("csv_file", help="CSVファイルのパス")
    parser.add_argument("--output-dir", default="batch", help="出力ディレクトリ（デフォルト: batch）")
    parser.add_argument("--chunk-size", type=int, default=10000, help="チャンクサイズ（デフォルト: 10000）")
    parser.add_argument("--limit", type=int, help="生成する件数の上限")
    
    args = parser.parse_args()
    
    generate_batch_jsonl(args.csv_file, args.output_dir, args.chunk_size, args.limit)

if __name__ == "__main__":
    main()
