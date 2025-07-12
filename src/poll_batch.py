#!/usr/bin/env python3
"""
job-info.jsonlの各ジョブをポーリングし、完了したら結果をダウンロードするスクリプト
"""

import os
import json
import sys
import time
import argparse
import tempfile
from datetime import datetime
from pathlib import Path
from google import genai

DEFAULT_JOB_INFO_FILE = "job-info.jsonl"
POLL_INTERVAL = 30  # 30秒間隔でポーリング

def load_jobs_from_jsonl(job_info_file):
    """job-info.jsonlからジョブ情報を読み込む"""
    if not os.path.exists(job_info_file):
        print(f"エラー: ジョブ情報ファイルが見つかりません: {job_info_file}", file=sys.stderr)
        return []
    
    jobs = []
    try:
        with open(job_info_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        job_record = json.loads(line)
                        job_record['_line_num'] = line_num  # 行番号を記録
                        jobs.append(job_record)
                    except json.JSONDecodeError as e:
                        print(f"警告: {line_num}行目のJSON解析に失敗: {e}", file=sys.stderr)
    except Exception as e:
        print(f"エラー: ジョブ情報ファイルの読み込みに失敗: {e}", file=sys.stderr)
        return []
    
    return jobs

def get_pending_jobs(jobs):
    """完了していないジョブのリストを取得"""
    return [job for job in jobs if 'completed_at' not in job]

def update_job_completion(job_info_file, jobs, job_index, completed_at):
    """指定されたジョブに完了時間を追加してJSONLファイルを更新"""
    # 該当ジョブに完了時間を追加
    jobs[job_index]['completed_at'] = completed_at
    
    # 一時ファイルに新しい内容を書き込み
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, 
                                       dir=os.path.dirname(job_info_file),
                                       prefix=f"{os.path.basename(job_info_file)}.tmp") as f:
            temp_file = f.name
            for job in jobs:
                # _line_numは内部管理用なので除外
                job_data = {k: v for k, v in job.items() if k != '_line_num'}
                json.dump(job_data, f, ensure_ascii=False)
                f.write('\n')
        
        # 元ファイルを削除して一時ファイルをリネーム
        os.remove(job_info_file)
        os.rename(temp_file, job_info_file)
        
    except Exception as e:
        # エラー時は一時ファイルを削除
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        raise e

def download_job_results(client, job, input_file_path):
    """ジョブの結果をダウンロード"""
    try:
        # ジョブの最新状態を取得
        batch_job = client.batches.get(name=job['job_name'])
        
        if batch_job.state.name != "JOB_STATE_SUCCEEDED":
            print(f"  警告: ジョブが成功していません: {batch_job.state.name}")
            if batch_job.error:
                print(f"  エラー詳細: {batch_job.error}")
            return False
        
        # 結果ファイルをダウンロード
        result_file_name = batch_job.dest.file_name
        print(f"  結果ファイルをダウンロード中: {result_file_name}")
        
        file_content_bytes = client.files.download(file=result_file_name)
        file_content = file_content_bytes.decode("utf-8")
        
        # ダウンロード先パスを決定（batchディレクトリ内のresults/）
        input_path = Path(input_file_path)
        # input_fileが "batch/003.jsonl" の場合、batch/results/ にする
        results_dir = input_path.parent / "results"
        results_dir.mkdir(exist_ok=True)
        
        # ファイル名は input_path.name を使用
        output_file = results_dir / input_path.name
        
        # 結果を保存
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(file_content)
        
        print(f"  結果を保存しました: {output_file}")
        return True
        
    except Exception as e:
        print(f"  エラー: 結果のダウンロードに失敗: {e}")
        return False

def poll_jobs(job_info_file, client):
    """ジョブをポーリングして完了したものを処理"""
    completed_states = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
    
    while True:
        # 最新のジョブ情報を読み込み
        jobs = load_jobs_from_jsonl(job_info_file)
        if not jobs:
            print("ジョブが見つかりません")
            break
        
        # 未完了のジョブを取得
        pending_jobs = get_pending_jobs(jobs)
        if not pending_jobs:
            print("すべてのジョブが完了しています")
            break
        
        print(f"\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"ポーリング中: {len(pending_jobs)}件のジョブ")
        
        # 各未完了ジョブの状態をチェック
        newly_completed = 0
        for i, job in enumerate(jobs):
            if 'completed_at' in job:
                continue  # 既に完了済み
            
            try:
                batch_job = client.batches.get(name=job['job_name'])
                current_state = batch_job.state.name
                
                print(f"  {job['input_file']}: {current_state}")
                
                if current_state in completed_states:
                    # ジョブ完了
                    completed_at = datetime.now().isoformat()
                    
                    if current_state == "JOB_STATE_SUCCEEDED":
                        # 結果をダウンロード
                        if download_job_results(client, job, job['input_file']):
                            print(f"  ✓ ダウンロード完了")
                        else:
                            print(f"  ✗ ダウンロード失敗")
                    else:
                        print(f"  ✗ ジョブ失敗: {current_state}")
                        if batch_job.error:
                            print(f"    エラー: {batch_job.error}")
                    
                    # 完了時間を記録
                    update_job_completion(job_info_file, jobs, i, completed_at)
                    newly_completed += 1
                
            except Exception as e:
                print(f"  エラー: {job['input_file']} のポーリングに失敗: {e}")
        
        if newly_completed > 0:
            print(f"新たに完了: {newly_completed}件")
            # ジョブ情報を再読み込みして次のループへ
            continue
        
        # 未完了ジョブがまだある場合は待機
        remaining = len(get_pending_jobs(load_jobs_from_jsonl(job_info_file)))
        if remaining > 0:
            print(f"残り{remaining}件のジョブを待機中...")
            for i in range(POLL_INTERVAL, -1, -1):
                print(f"\r次回ポーリングまで {i:2d}秒", end="", flush=True)
                time.sleep(1)
            print()

def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(
        description="job-info.jsonlの各ジョブをポーリングし、完了したら結果をダウンロード"
    )
    
    parser.add_argument(
        "--job-info",
        default=DEFAULT_JOB_INFO_FILE,
        help=f"ジョブ情報JSONLファイル（デフォルト: {DEFAULT_JOB_INFO_FILE}）"
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
    
    # ジョブをポーリング
    try:
        poll_jobs(args.job_info, client)
        print("\nポーリング完了")
    except KeyboardInterrupt:
        print("\nポーリングが中断されました")
        sys.exit(1)
    except Exception as e:
        print(f"\nエラー: ポーリング中に予期しないエラーが発生: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
