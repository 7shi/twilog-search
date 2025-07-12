#!/usr/bin/env python3
"""
複数のJSONLファイルをGemini Batchジョブとして投入するスクリプト
"""

import os
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from google import genai
from google.genai import types

MODEL_ID = "gemini-2.5-flash-lite-preview-06-17"
DEFAULT_JOB_INFO_FILE = "job-info.jsonl"

def load_existing_jobs(job_info_file):
    """既存のジョブ情報を読み込む"""
    if not os.path.exists(job_info_file):
        return {}
    
    jobs = {}
    try:
        with open(job_info_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    job_record = json.loads(line)
                    jobs[job_record['input_file']] = job_record
    except Exception as e:
        print(f"警告: ジョブ情報ファイルの読み込みに失敗: {e}", file=sys.stderr)
    
    return jobs

def save_job_record(job_record, job_info_file):
    """ジョブレコードをJSONLファイルに追記"""
    with open(job_info_file, 'a', encoding='utf-8') as f:
        json.dump(job_record, f, ensure_ascii=False)
        f.write('\n')

def submit_batch_job(input_file, client, existing_jobs, job_info_file):
    """単一ファイルのバッチジョブを投入"""
    input_path = Path(input_file)
    
    if not input_path.exists():
        print(f"エラー: 入力ファイルが見つかりません: {input_file}", file=sys.stderr)
        return False
    
    # 既存ジョブチェック
    if input_file in existing_jobs:
        job_record = existing_jobs[input_file]
        print(f"スキップ: {input_file} は既にジョブ投入済み (ジョブ名: {job_record['job_name']})")
        return True
    
    print(f"ファイルをアップロード中: {input_file}")
    try:
        uploaded_file = client.files.upload(
            file=str(input_path),
            config=types.UploadFileConfig(
                display_name=f"batch-input-{input_path.stem}",
                mime_type="jsonl"
            )
        )
        print(f"アップロード完了: {uploaded_file.name}")
        
        print(f"バッチジョブを作成中...")
        batch_job = client.batches.create(
            model=MODEL_ID,
            src=uploaded_file.name,
            config={
                "display_name": f"batch-job-{input_path.stem}",
            }
        )
        
        print(f"バッチジョブ作成成功: {batch_job.name}")
        
        # ジョブ情報を記録
        job_record = {
            "input_file": input_file,
            "job_name": batch_job.name,
            "uploaded_file_name": uploaded_file.name,
            "display_name": f"batch-job-{input_path.stem}",
            "created_at": datetime.now().isoformat()
        }
        
        save_job_record(job_record, job_info_file)
        print(f"ジョブ情報を保存: {job_info_file}")
        
        return True
        
    except Exception as e:
        print(f"エラー: {input_file} の処理に失敗: {e}", file=sys.stderr)
        
        # アップロードしたファイルがあれば削除を試行
        try:
            if 'uploaded_file' in locals():
                print(f"アップロードファイルを削除中: {uploaded_file.name}")
                client.files.delete(name=uploaded_file.name)
                print("削除完了")
        except Exception as delete_error:
            print(f"削除失敗: {delete_error}", file=sys.stderr)
        
        return False

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="複数のJSONLファイルをGemini Batchジョブとして投入"
    )
    
    parser.add_argument(
        "input_files", 
        nargs='+', 
        help="投入するJSONLファイルのパス（複数指定可能）"
    )
    parser.add_argument(
        "--job-info", 
        default=DEFAULT_JOB_INFO_FILE,
        help=f"ジョブ情報を保存するJSONLファイル（デフォルト: {DEFAULT_JOB_INFO_FILE}）"
    )
    
    args = parser.parse_args()
    
    # Gemini APIキーの確認
    if "GEMINI_API_KEY" not in os.environ:
        print("エラー: GEMINI_API_KEY環境変数が設定されていません", file=sys.stderr)
        sys.exit(1)
    
    # Geminiクライアント初期化
    try:
        client = genai.Client(
            api_key=os.environ["GEMINI_API_KEY"], 
            http_options={"api_version": "v1alpha"}
        )
    except Exception as e:
        print(f"エラー: Geminiクライアントの初期化に失敗: {e}", file=sys.stderr)
        sys.exit(1)
    
    # 既存ジョブ情報を読み込み
    existing_jobs = load_existing_jobs(args.job_info)
    print(f"既存ジョブ数: {len(existing_jobs)}")
    
    # 各ファイルを処理
    success_count = 0
    total_count = len(args.input_files)
    
    for input_file in args.input_files:
        print(f"\n[{success_count + 1}/{total_count}] 処理中: {input_file}")
        if submit_batch_job(input_file, client, existing_jobs, args.job_info):
            success_count += 1
    
    print(f"\n完了: {success_count}/{total_count} 件のジョブを投入しました")
    
    if success_count < total_count:
        sys.exit(1)

if __name__ == "__main__":
    main()