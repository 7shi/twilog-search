#!/usr/bin/env python3
"""
CSVファイルからタグを抽出し、JSONファイルに保存するスクリプト
"""

import argparse
import json
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from llm7shi.compat import generate_with_schema
from llm7shi import create_json_descriptions_prompt
from tqdm import tqdm
from data_csv import TwilogDataAccess, strip_content

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

def load_processed_content(csv_path: str, limit: int = None, offset: int = 0) -> list:
    """
    CSVファイルからデータを読み込み、前処理済みコンテンツを生成する
    
    Args:
        csv_path: CSVファイルのパス
        limit: 取得する件数の上限
        offset: 取得開始位置
        
    Returns:
        (post_id, processed_content)のリスト
    """
    data_access = TwilogDataAccess(csv_path)
    
    # 全投稿IDを取得
    all_post_ids = sorted(data_access.posts_data.keys())
    
    # offset/limitの適用
    if offset > 0:
        all_post_ids = all_post_ids[offset:]
    if limit is not None:
        all_post_ids = all_post_ids[:limit]
    
    # 投稿データを取得して前処理
    result = []
    for post_id in all_post_ids:
        post_data = data_access.posts_data[post_id]
        content = post_data['content']
        
        # 前処理を適用（URL・メンション除去、ハッシュタグ保持）
        processed_content = strip_content(content)
        
        # 空文字でない場合のみ結果に追加
        if processed_content.strip():
            result.append((post_id, processed_content))
    
    return result

def get_processed_post_ids(output_dir: Path) -> set:
    """
    既存のJSONLファイルから処理済みpost_idのセットを取得する
    
    Args:
        output_dir: 出力ディレクトリのパス
        
    Returns:
        処理済みpost_idのセット
    """
    if not output_dir.exists():
        return set()
    
    processed_ids = set()
    try:
        # tags/ディレクトリ内の全*.jsonlファイルを処理
        for jsonl_file in output_dir.glob('*.jsonl'):
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        processed_ids.add(data['post_id'])
        return processed_ids
    except Exception as e:
        print(f"既存ファイル読み込みエラー: {e}")
        return set()

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

def extract_tags_from_csv(
    csv_path: str,
    output_dir: str,
    model: str = "ollama:qwen3:4b",
    limit: int = None,
    resume: bool = True
) -> None:
    """
    CSVファイルからタグを抽出してJSONLファイルに保存する
    
    Args:
        csv_path: CSVファイルのパス
        output_dir: 出力ディレクトリのパス
        model: 使用するLLMモデル
        limit: 処理する件数の上限
        resume: 中断・再開機能を使用するか
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # 既存データの確認
    existing_post_ids = get_processed_post_ids(output_path) if resume else set()
    if existing_post_ids:
        print(f"既存データ: {len(existing_post_ids)}件をスキップ")
    
    # データ読み込み（既存件数を考慮してLIMITを調整）
    print("CSVファイルからデータを読み込み中...")
    adjusted_limit = None
    if limit is not None:
        adjusted_limit = limit + len(existing_post_ids)
    
    data = load_processed_content(csv_path, adjusted_limit)
    total_posts = len(data)
    print(f"読込件数: {total_posts}")
    
    # 未処理データのフィルタリング
    if resume:
        data = [(post_id, content) for post_id, content in data 
                if post_id not in existing_post_ids]
        print(f"未処理データ: {len(data)}件")
    
    if not data:
        print("処理対象のデータがありません")
        return
    
    # 1件ずつ処理・保存
    processed_count = 0
    total_processed = len(existing_post_ids)  # 既存処理件数を含む
    
    for post_id, content in tqdm(data, desc="タグ付け中"):
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
            
            # ファイルインデックスを計算（1000件ごと）
            file_index = total_processed // 1000
            
            # 1件ずつ追記保存
            save_tag_record(record, output_path, file_index)
            processed_count += 1
            total_processed += 1
        else:
            print(f"分析に失敗しました: post_id={post_id}")
    
    print(f"タグ付け完了: {processed_count}件を処理しました")

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="CSVファイルからタグを抽出してJSONファイルに保存"
    )
    
    parser.add_argument("csv_file", help="CSVファイルのパス（デフォルト: twilog.csv）", nargs='?', default="twilog.csv")
    parser.add_argument("--output", default="tags", help="出力ディレクトリのパス（デフォルト: tags）")
    parser.add_argument("--model", default="ollama:qwen3:4b", help="使用するLLMモデル（デフォルト: ollama:qwen3:4b）")
    parser.add_argument("--limit", type=int, help="処理する件数の上限")
    parser.add_argument("--no-resume", action="store_true", help="中断・再開機能を無効にする")
    
    args = parser.parse_args()
    
    extract_tags_from_csv(
        args.csv_file,
        args.output,
        args.model,
        args.limit,
        not args.no_resume
    )

if __name__ == "__main__":
    main()
