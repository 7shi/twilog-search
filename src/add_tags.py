#!/usr/bin/env python3
"""
CSVファイルのデータにタグを付けて、分割JSONLファイルに保存するスクリプト
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from tqdm import tqdm
from data_csv import TwilogDataAccess, strip_content
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt

class TweetTagAnalysisSchema(BaseModel):
    reasoning: str = Field(description="内容についての検討")
    summary: str = Field(description="簡潔な一行要約（日本語、30文字以内）")
    tags: List[str] = Field(description="投稿内容を表すタグのリスト（例：プログラミング、機械学習、日常、思考、技術解説）")

json_descriptions = "\n".join(create_json_descriptions_prompt(TweetTagAnalysisSchema).strip().splitlines()[1:])

PROMPT = f"""
下記のツイート内容を分析し、情報を抽出してください。

### 分析項目
{json_descriptions}

### 指示
- 日本語で分析結果を記述してください
- 情報が明記されていない場合は推測せず、適切なデフォルト値を使用してください
- タグが不明な場合は空のリストを返してください
- タグは投稿の主要なトピックや分野を表すものにしてください
""".strip()

def analyze_content_with_llm(content: str, model: str = "ollama:qwen3:4b") -> dict:
    """投稿内容をLLMで分析する"""
    content_part = f"### ツイート内容\n{content}".rstrip()
    
    try:
        response = generate_with_schema(
            [PROMPT, content_part],
            schema=TweetTagAnalysisSchema,
            model=model,
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"LLM分析でエラーが発生しました: {e}")
        return None

def load_data_from_csv(csv_path):
    """
    CSVファイルからデータを読み込む
    
    Args:
        csv_path: CSVファイルのパス
        
    Returns:
        (post_id, content)のリスト
    """
    data_access = TwilogDataAccess(csv_path)
    
    # 全投稿データを取得
    data = []
    for post_id, post_data in tqdm(data_access.posts_data.items(), desc="データ確認"):
        content = strip_content(post_data['content'])
        if content:  # 空でない場合のみ追加
            data.append((post_id, content))
    return data

def save_tag_record(record: dict, output_dir: Path, file_index: int) -> None:
    """
    1件のタグレコードをJSONL形式で追記保存する
    
    Args:
        record: タグレコード
        output_dir: 出力ディレクトリのパス
        file_index: ファイルインデックス（0000, 0001, ...）
    """
    output_file = output_dir / f"{file_index:04d}.jsonl"
    try:
        with open(output_file, 'a', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False)
            f.write('\n')
    except Exception as e:
        print(f"保存エラー: {e}")

def get_target_file_index(file_counts: dict, chunk_size: int) -> int:
    """
    保存対象のファイルインデックスを決定する
    
    Args:
        file_counts: {file_index: 行数}の辞書
        chunk_size: チャンクサイズ
        
    Returns:
        保存対象のファイルインデックス
    """
    if not file_counts:
        return 0
    
    # 0から順番に確認し、chunk_size未満のファイルがあればそれを使用
    max_index = max(file_counts.keys())
    for i in range(max_index + 1):
        if i in file_counts:
            if file_counts[i] < chunk_size:
                return i
        else:
            # 中間が抜けている場合、その番号を使用
            return i
    
    # すべてのファイルがchunk_size以上なら次のインデックス
    return max_index + 1

def create_metadata(total_posts, chunk_size, output_dir, csv_path):
    """
    メタデータファイルを作成する
    
    Args:
        total_posts: 総投稿数
        chunk_size: チャンクサイズ
        output_dir: 出力ディレクトリ
        csv_path: CSVファイルのパス
    """
    import os
    
    chunks = (total_posts + chunk_size - 1) // chunk_size
    
    # CSVファイルのパスをoutput_dirの親ディレクトリからの相対パスに変換
    csv_relative_path = os.path.relpath(csv_path, output_dir.parent)
    
    metadata = {
        "total_posts": total_posts,
        "chunk_size": chunk_size,
        "chunks": chunks,
        "csv_path": csv_relative_path
    }
    
    with open(output_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def add_tags_from_csv(csv_path, output_dir, model="ollama:qwen3:4b", chunk_size=1000, limit=None):
    """
    CSVファイルからタグを抽出してJSONLファイルに保存する
    
    Args:
        csv_path: CSVファイルのパス
        output_dir: 出力ディレクトリのパス
        model: 使用するLLMモデル
        chunk_size: チャンクサイズ
        limit: 処理する件数の上限
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # データ読み込み
    data = load_data_from_csv(csv_path)
    total_posts = len(data)
    all_post_ids = set(post_id for post_id, _ in data)
    print(f"総投稿数: {total_posts}")
    
    # 既存のJSONLファイルからpost_idを収集し、ファイルごとの行数を記録
    processed_post_ids = set()
    file_counts = {}  # {file_index: 行数}
    if output_path.exists():
        files = sorted(output_path.glob("*.jsonl"))
        for jsonl_file in tqdm(files, desc="既存確認"):
            try:
                # ファイル名からインデックスを抽出
                file_index = int(jsonl_file.stem)
                line_count = 0
                
                with open(jsonl_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            line_count += 1
                            record = json.loads(line)
                            post_id = record['post_id']
                            # 重複チェック
                            if post_id in processed_post_ids:
                                print(f"\nエラー: post_idに重複があります: {post_id}")
                                print(f"ファイル: {jsonl_file}")
                                return
                            processed_post_ids.add(post_id)
                
                file_counts[file_index] = line_count
            except Exception as e:
                print(f"警告: {jsonl_file}の読み込みに失敗: {e}")
    
    # 変換済み・残りpost_id数を表示
    remaining_post_ids = all_post_ids - processed_post_ids
    print(f"変換済み: {len(processed_post_ids)}件")
    print(f"残り: {len(remaining_post_ids)}件")
    
    # 全件完了していれば終了
    if not remaining_post_ids:
        print("すべてのpost_idが変換済みです")
        return
    
    # 残りのpost_idのみを対象に変換
    remaining_data = [(post_id, content) for post_id, content in data if post_id in remaining_post_ids]
    
    # post_idでソート
    remaining_data.sort(key=lambda x: x[0])
    
    # limit制限の適用
    if limit is not None and len(remaining_data) > limit:
        remaining_data = remaining_data[:limit]
        print(f"limit制限により{limit}件に制限されました")
    
    # 1件ずつ処理・保存
    processed_count = 0
    current_file_index = get_target_file_index(file_counts, chunk_size)
    current_file_count = file_counts.get(current_file_index, 0)
    
    for post_id, content in tqdm(remaining_data, desc="タグ付け中"):
        # LLMで分析
        analysis = analyze_content_with_llm(content, model)
        
        if analysis:
            # フラットな構造でレコード作成
            record = {
                'post_id': post_id,
                'reasoning': analysis.get('reasoning', ''),
                'summary': analysis.get('summary', ''),
                'tags': analysis.get('tags', [])
            }
            
            # 1件ずつ追記保存
            save_tag_record(record, output_path, current_file_index)
            processed_count += 1
            current_file_count += 1
            
            # ファイルがchunk_sizeに達したら次のファイルに移行
            if current_file_count >= chunk_size:
                file_counts[current_file_index] = current_file_count
                current_file_index = get_target_file_index(file_counts, chunk_size)
                current_file_count = file_counts.get(current_file_index, 0)
        else:
            print(f"分析に失敗しました: post_id={post_id}")
    
    print(f"タグ付け完了: {processed_count}件を処理しました")
    
    # メタデータ作成
    create_metadata(total_posts, chunk_size, output_path, csv_path)
    print(f"出力先: {output_dir}")

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="CSVファイルからタグを抽出してJSONLファイルに保存"
    )
    
    parser.add_argument("csv_file", help="CSVファイルのパス")
    parser.add_argument("--output-dir", default="tags", help="出力ディレクトリ（デフォルト: tags）")
    parser.add_argument("--model", default="ollama:qwen3:4b", help="使用するLLMモデル（デフォルト: ollama:qwen3:4b）")
    parser.add_argument("--chunk-size", type=int, default=1000, help="チャンクサイズ（デフォルト: 1000）")
    parser.add_argument("--limit", type=int, help="処理する件数の上限")
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print("タグ付け開始:", start_time)
    
    add_tags_from_csv(
        args.csv_file,
        args.output_dir,
        args.model,
        args.chunk_size,
        args.limit
    )
    
    end_time = datetime.now()
    elapsed = end_time - start_time
    print("タグ付け完了:", end_time)
    print(f"所要時間: {elapsed} ({elapsed.total_seconds():.2f}秒)")

if __name__ == "__main__":
    main()
