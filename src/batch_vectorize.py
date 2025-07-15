#!/usr/bin/env python3
"""
batch/results.jsonlのreasoningとsummaryをRuri3でベクトル化し、分割safetensorsファイルに保存するスクリプト
"""

import argparse
import json
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# vectorize.pyから汎用関数をインポート
from vectorize import vectorize_data

def load_data_from_jsonl(jsonl_path, field_name):
    """
    JSONLファイルから指定フィールドのデータを読み込む
    
    Args:
        jsonl_path: JSONLファイルのパス
        field_name: 抽出するフィールド名（"reasoning" または "summary"）
        
    Returns:
        (key, content)のリスト
    """
    data = []
    
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in tqdm(f, desc=f"{field_name}データ読み込み"):
            try:
                record = json.loads(line.strip())
                if 'key' in record and field_name in record:
                    key = record['key']
                    content = record[field_name]
                    
                    # 空でない場合のみ追加
                    if content and content.strip():
                        data.append((key, content.strip()))
            except json.JSONDecodeError as e:
                print(f"JSON解析エラー: {e}")
                continue
    
    return data

def vectorize_batch_field(jsonl_path, field_name, chunk_size=1000, device="cpu", resume=True):
    """
    batch/results.jsonlの指定フィールドをベクトル化する
    
    Args:
        jsonl_path: JSONLファイルのパス
        field_name: ベクトル化するフィールド名（"reasoning" または "summary"）
        chunk_size: チャンクサイズ
        device: 使用するデバイス
        resume: 中断・再開機能を使用するか
    """
    # JSONLファイルと同じディレクトリにフィールド専用ディレクトリを作成
    jsonl_dir = Path(jsonl_path).parent
    output_dir = jsonl_dir / field_name
    
    print(f"\n=== {field_name}フィールドのベクトル化 ===")
    print(f"入力ファイル: {jsonl_path}")
    print(f"出力ディレクトリ: {output_dir}")
    
    # データ読み込み
    data = load_data_from_jsonl(jsonl_path, field_name)
    
    if not data:
        print(f"警告: {field_name}フィールドに有効なデータが見つかりませんでした")
        return
    
    # 汎用ベクトル化関数を呼び出し
    vectorize_data(
        data=data,
        output_dir=str(output_dir),
        source_path=jsonl_path,
        source_type="jsonl",
        chunk_size=chunk_size,
        device=device,
        resume=resume
    )

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="batch/results.jsonlのreasoningとsummaryをベクトル化してsafetensorsファイルに保存"
    )
    
    parser.add_argument("jsonl_file", help="JSONLファイルのパス")
    parser.add_argument("--field", choices=["reasoning", "summary", "both"], default="both", 
                       help="ベクトル化するフィールド（デフォルト: both）")
    parser.add_argument("--chunk-size", type=int, default=1000, help="チャンクサイズ（デフォルト: 1000）")
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu", help="使用するデバイス")
    parser.add_argument("--no-resume", action="store_true", help="中断・再開機能を無効にする")
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print("バッチベクトル化開始:", start_time)
    
    # フィールドの選択
    fields_to_process = []
    if args.field == "both":
        fields_to_process = ["reasoning", "summary"]
    else:
        fields_to_process = [args.field]
    
    # 各フィールドを処理
    for field_name in fields_to_process:
        vectorize_batch_field(
            args.jsonl_file,
            field_name,
            args.chunk_size,
            args.device,
            not args.no_resume
        )
    
    end_time = datetime.now()
    elapsed = end_time - start_time
    print("\nバッチベクトル化完了:", end_time)
    print(f"所要時間: {elapsed} ({elapsed.total_seconds():.2f}秒)")

if __name__ == "__main__":
    main()