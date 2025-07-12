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
from rich.live import Live
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

DEFAULT_JOB_INFO_FILE = "job-info.jsonl"
POLL_INTERVAL = 30  # 30秒間隔でポーリング

console = Console()

def create_job_status_display(jobs, last_update, countdown=None):
    """ジョブステータスのテーブル表示を作成"""
    table = Table(title="バッチジョブ監視状況")
    table.add_column("ファイル", style="cyan")
    table.add_column("状態", style="magenta")
    table.add_column("作成日時", style="dim")
    table.add_column("完了日時", style="green")
    table.add_column("所要時間", style="yellow")
    
    completed_count = 0
    for job in jobs:
        input_file = job['input_file']
        
        if 'completed_at' in job:
            completed_count += 1
            final_state = job.get('final_state', '')
            if final_state == 'JOB_STATE_SUCCEEDED':
                status = "✓ 成功"
                status_style = "green"
            elif final_state == 'JOB_STATE_FAILED':
                status = "✗ 失敗"
                status_style = "red"
            elif final_state == 'JOB_STATE_CANCELLED':
                status = "⊘ キャンセル"
                status_style = "orange1"
            else:
                # 後方互換性のため
                status = "✓ 完了"
                status_style = "green"
        else:
            status = "⏳ 処理中"
            status_style = "yellow"
        
        created_at = job.get('created_at', '')[:19].replace('T', ' ')
        completed_at = job.get('completed_at', '')[:19].replace('T', ' ') if 'completed_at' in job else ''
        
        # 所要時間の表示
        duration_display = ""
        if 'duration_seconds' in job:
            duration_sec = job['duration_seconds']
            hours = duration_sec // 3600
            minutes = (duration_sec % 3600) // 60
            seconds = duration_sec % 60
            if hours > 0:
                duration_display = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                duration_display = f"{minutes}m {seconds}s"
            else:
                duration_display = f"{seconds}s"
        
        table.add_row(
            input_file,
            Text(status, style=status_style),
            created_at,
            completed_at,
            duration_display
        )
    
    # サマリー情報
    total_jobs = len(jobs)
    pending_jobs = total_jobs - completed_count
    
    summary = Text()
    summary.append(f"総ジョブ数: {total_jobs} | ", style="bold")
    summary.append(f"完了: {completed_count} | ", style="green bold")
    summary.append(f"残り: {pending_jobs}", style="yellow bold")
    
    if countdown is not None:
        summary.append(f" | 次回ポーリング: {countdown}秒", style="cyan")
    
    # パネルに包む
    content = [
        Text(f"最終更新: {last_update}", style="dim"),
        Text(""),
        summary,
        Text(""),
        table
    ]
    
    if pending_jobs == 0:
        content.append(Text(""))
        content.append(Text("🎉 すべてのジョブが完了しました！", style="green bold"))
    
    from rich.columns import Columns
    from rich.align import Align
    
    return Panel(
        Align.center(Columns(content, equal=True, expand=True)),
        title="Gemini Batch Job Monitor",
        border_style="blue"
    )

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

def update_job_completion(job_info_file, jobs, job_index, completed_at_datetime, final_state):
    """指定されたジョブに完了時間、所要時間、最終状態を追加してJSONLファイルを更新"""
    # 該当ジョブに完了時間と最終状態を追加
    jobs[job_index]['completed_at'] = completed_at_datetime.isoformat()
    jobs[job_index]['final_state'] = final_state
    
    # 所要時間を計算
    if 'created_at' in jobs[job_index]:
        try:
            created_time = datetime.fromisoformat(jobs[job_index]['created_at'])
            duration = completed_at_datetime - created_time
            jobs[job_index]['duration_seconds'] = int(duration.total_seconds())
        except Exception:
            # 日時解析に失敗した場合はスキップ
            pass
    
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
            return False, f"ジョブが成功していません: {batch_job.state.name}"
        
        # 結果ファイルをダウンロード
        result_file_name = batch_job.dest.file_name
        file_content_bytes = client.files.download(file=result_file_name)
        file_content = file_content_bytes.decode("utf-8")
        
        # ダウンロード先パスを決定（batchディレクトリ内のresults/）
        input_path = Path(input_file_path)
        results_dir = input_path.parent / "results"
        results_dir.mkdir(exist_ok=True)
        
        # ファイル名は input_path.name を使用
        output_file = results_dir / input_path.name
        
        # 結果を保存
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(file_content)
        
        return True, str(output_file)
        
    except Exception as e:
        return False, f"結果のダウンロードに失敗: {e}"

def poll_jobs(job_info_file, client):
    """ジョブをポーリングして完了したものを処理"""
    completed_states = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED"}
    
    with Live(console=console, refresh_per_second=1) as live:
        while True:
            # 最新のジョブ情報を読み込み
            jobs = load_jobs_from_jsonl(job_info_file)
            if not jobs:
                live.update(Text("エラー: ジョブが見つかりません", style="red bold"))
                break
            
            # 未完了のジョブを取得
            pending_jobs = get_pending_jobs(jobs)
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if not pending_jobs:
                live.update(create_job_status_display(jobs, current_time))
                break
            
            # 表示を更新
            live.update(create_job_status_display(jobs, current_time))
            
            # 各未完了ジョブの状態をチェック
            newly_completed = 0
            for i, job in enumerate(jobs):
                if 'completed_at' in job:
                    continue  # 既に完了済み
                
                try:
                    batch_job = client.batches.get(name=job['job_name'])
                    current_state = batch_job.state.name
                    
                    if current_state in completed_states:
                        # ジョブ完了（成功、失敗、キャンセル問わず）
                        completed_at = datetime.now()
                        
                        if current_state == "JOB_STATE_SUCCEEDED":
                            # 結果をダウンロード
                            success, message = download_job_results(client, job, job['input_file'])
                            # ダウンロード結果は内部処理のみ
                        
                        # 完了時間と最終状態を記録
                        update_job_completion(job_info_file, jobs, i, completed_at, current_state)
                        newly_completed += 1
                    
                except Exception as e:
                    # エラーは内部処理のみ、表示には影響しない
                    pass
            
            if newly_completed > 0:
                # ジョブ情報を再読み込みして次のループへ
                continue
            
            # 未完了ジョブがまだある場合は待機
            remaining = len(get_pending_jobs(load_jobs_from_jsonl(job_info_file)))
            if remaining > 0:
                for countdown in range(POLL_INTERVAL, -1, -1):
                    live.update(create_job_status_display(jobs, current_time, countdown))
                    time.sleep(1)

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
