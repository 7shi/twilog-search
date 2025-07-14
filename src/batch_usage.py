#!/usr/bin/env python3
"""
バッチ結果のusageMetadata構造をチェックするスクリプト
"""

import json
import sys
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# クエリファイルのキャッシュ
query_cache = {}


def check_usage_metadata_structure(usage_metadata: Dict[str, Any], response_data: Dict[str, Any]) -> List[str]:
    """
    usageMetadataの構造をチェックし、問題があればエラーメッセージを返す
    """
    errors = []
    
    # promptFeedbackでブロックされた場合の処理
    is_blocked = 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']
    
    # 必須フィールドの存在チェック
    required_fields = ['totalTokenCount', 'promptTokenCount']
    if not is_blocked:
        required_fields.append('candidatesTokenCount')
    
    for field in required_fields:
        if field not in usage_metadata:
            errors.append(f"必須フィールド '{field}' が存在しません")
        elif not isinstance(usage_metadata[field], int):
            errors.append(f"フィールド '{field}' は整数である必要があります")
    
    # promptTokensDetailsの存在チェック
    if 'promptTokensDetails' not in usage_metadata:
        errors.append("必須フィールド 'promptTokensDetails' が存在しません")
    else:
        prompt_details = usage_metadata['promptTokensDetails']
        if not isinstance(prompt_details, list):
            errors.append("'promptTokensDetails' は配列である必要があります")
        else:
            for i, detail in enumerate(prompt_details):
                if not isinstance(detail, dict):
                    errors.append(f"promptTokensDetails[{i}] は辞書である必要があります")
                    continue
                
                if 'tokenCount' not in detail:
                    errors.append(f"promptTokensDetails[{i}] に 'tokenCount' がありません")
                elif not isinstance(detail['tokenCount'], int):
                    errors.append(f"promptTokensDetails[{i}].tokenCount は整数である必要があります")
                
                if 'modality' not in detail:
                    errors.append(f"promptTokensDetails[{i}] に 'modality' がありません")
                elif not isinstance(detail['modality'], str):
                    errors.append(f"promptTokensDetails[{i}].modality は文字列である必要があります")
    
    # トークン数の整合性チェック
    if len(errors) == 0:  # 基本構造に問題がない場合のみ
        total = usage_metadata.get('totalTokenCount', 0)
        prompt = usage_metadata.get('promptTokenCount', 0)
        candidates = usage_metadata.get('candidatesTokenCount', 0)
        thoughts = usage_metadata.get('thoughtsTokenCount', 0)  # 思考トークン（存在しない場合は0）
        
        if is_blocked:
            # ブロックされた場合はcandidatesTokenCountは0として扱う
            expected_total = prompt + thoughts
            if total != expected_total:
                thoughts_info = f" + thoughts({thoughts})" if thoughts > 0 else ""
                errors.append(f"トークン数の不整合（ブロック時）: total({total}) != prompt({prompt}){thoughts_info}")
        else:
            expected_total = prompt + candidates + thoughts
            if total != expected_total:
                thoughts_info = f" + thoughts({thoughts})" if thoughts > 0 else ""
                errors.append(f"トークン数の不整合: total({total}) != prompt({prompt}) + candidates({candidates}){thoughts_info}")
    
    return errors


def print_errors_and_violations(results: Dict[str, Any], show_content: bool = False) -> None:
    """
    エラーと構造違反を表示する
    """
    if results['errors']:
        print("エラー:")
        for error in results['errors']:
            print(f"  - {error}")
        print()
    
    if results['structure_violations']:
        print("構造違反:")
        for violation in results['structure_violations']:
            print(f"  - {violation}")
        print()
    
    # エラーがある行の内容を表示
    if show_content and results['error_lines']:
        print("エラーがある行の内容:")
        for line_num, content in results['error_lines']:
            print(f"  行{line_num}: {content}")
        print()


def print_blocked_details(results: Dict[str, Any]) -> None:
    """
    ブロックされた行の詳細を表示する
    """
    if results['blocked_details']:
        print("ブロックされた行の詳細:")
        for detail in results['blocked_details']:
            file_name = Path(detail['file_path']).name
            print(f"\n  {file_name}:行{detail['line_number']} - {detail['block_reason']}")
            if detail['query']:
                print(f"    クエリ: {detail['query']}")
            if detail['response']:
                print(f"    レスポンス: {detail['response']}")
        print()


def load_jsonl_as_dict(file_path: str) -> Dict[str, Any]:
    """
    JSONLファイルを読み込み、key→dictのマッピングを作成する
    """
    result = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    key = data.get('key')
                    if key:
                        result[key] = data
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return result


def get_query_dict(result_file_path: str) -> Dict[str, Any]:
    """
    クエリファイルをキャッシュ付きで読み込む
    """
    if result_file_path in query_cache:
        return query_cache[result_file_path]
    
    result_path = Path(result_file_path)
    query_file = result_path.parent.parent / result_path.name
    
    if query_file.exists():
        query_dict = load_jsonl_as_dict(str(query_file))
        query_cache[result_file_path] = query_dict
        return query_dict
    
    return {}


def get_query_from_parent_dir(result_file_path: str, result_key: str) -> Optional[str]:
    """
    結果ファイルの親ディレクトリから対応するクエリファイルを読み取り、keyが一致するクエリを返す
    """
    try:
        query_dict = get_query_dict(result_file_path)
        if result_key in query_dict:
            return json.dumps(query_dict[result_key], ensure_ascii=False)
        return f"key {result_key} が見つかりません"
    except Exception as e:
        return f"クエリ取得エラー: {str(e)}"


def analyze_jsonl_file(file_path: str, show_content: bool = False) -> Dict[str, Any]:
    """
    JSONLファイルを解析してusageMetadataの構造をチェックする
    """
    results = {
        'total_lines': 0,
        'valid_lines': 0,
        'invalid_lines': 0,
        'thoughts_lines': 0,
        'blocked_lines': 0,
        'blocked_details': [],
        'errors': [],
        'structure_violations': [],
        'error_lines': []
    }
    
    # レスポンスファイルをkey→dictのマッピングとして読み込む
    response_dict = load_jsonl_as_dict(file_path)
    
    # 行番号付きでファイルを再読み込み（表示用）
    line_mapping = {}
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                results['total_lines'] += 1
                
                try:
                    # JSON解析
                    data = json.loads(line.strip())
                    key = data.get('key')
                    if key:
                        line_mapping[key] = (line_num, line.strip())
                    
                except json.JSONDecodeError as e:
                    results['invalid_lines'] += 1
                    results['errors'].append(f"行{line_num}: JSON解析エラー: {str(e)}")
                    if show_content:
                        results['error_lines'].append((line_num, line.strip()))
                except Exception as e:
                    results['invalid_lines'] += 1
                    results['errors'].append(f"行{line_num}: 予期しないエラー: {str(e)}")
                    if show_content:
                        results['error_lines'].append((line_num, line.strip()))
    
    except FileNotFoundError:
        results['errors'].append(f"ファイルが見つかりません: {file_path}")
    except Exception as e:
        results['errors'].append(f"ファイル読み込みエラー: {str(e)}")
    
    # dictベースでの分析
    for key, data in response_dict.items():
        line_num, line_content = line_mapping.get(key, (0, ""))
        
        # usageMetadataの存在チェック
        if 'response' not in data:
            results['structure_violations'].append(f"行{line_num}: 'response' フィールドが存在しません")
            results['invalid_lines'] += 1
            if show_content:
                results['error_lines'].append((line_num, line_content))
            continue
        
        if 'usageMetadata' not in data['response']:
            results['structure_violations'].append(f"行{line_num}: 'usageMetadata' フィールドが存在しません")
            results['invalid_lines'] += 1
            if show_content:
                results['error_lines'].append((line_num, line_content))
            continue
        
        # usageMetadataの構造チェック
        usage_metadata = data['response']['usageMetadata']
        response_data = data['response']
        structure_errors = check_usage_metadata_structure(usage_metadata, response_data)
        
        # thoughtsTokenCountがある行をカウント
        if 'thoughtsTokenCount' in usage_metadata and usage_metadata['thoughtsTokenCount'] > 0:
            results['thoughts_lines'] += 1
        
        # ブロックされた行をカウント
        if 'promptFeedback' in response_data and 'blockReason' in response_data['promptFeedback']:
            results['blocked_lines'] += 1
            block_reason = response_data['promptFeedback']['blockReason']
            query = get_query_from_parent_dir(file_path, key)
            results['blocked_details'].append({
                'line_number': line_num,
                'block_reason': block_reason,
                'query': query,
                'response': line_content,
                'file_path': file_path
            })
        
        if structure_errors:
            results['invalid_lines'] += 1
            for error in structure_errors:
                results['structure_violations'].append(f"行{line_num}: {error}")
            if show_content:
                results['error_lines'].append((line_num, line_content))
        else:
            results['valid_lines'] += 1
    
    return results


def main():
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="バッチ結果のusageMetadata構造をチェックするスクリプト"
    )
    parser.add_argument(
        "jsonl_files",
        nargs="+",
        help="分析対象のJSONLファイルパス（複数可）"
    )
    
    args = parser.parse_args()
    
    # 複数ファイルの処理
    all_results = {
        'total_lines': 0,
        'valid_lines': 0,
        'invalid_lines': 0,
        'thoughts_lines': 0,
        'blocked_lines': 0,
        'blocked_details': [],
        'errors': [],
        'structure_violations': [],
        'error_lines': []
    }
    
    for jsonl_file in args.jsonl_files:
        results = analyze_jsonl_file(jsonl_file, False)
        
        # 結果をマージ
        all_results['total_lines'] += results['total_lines']
        all_results['valid_lines'] += results['valid_lines']
        all_results['invalid_lines'] += results['invalid_lines']
        all_results['thoughts_lines'] += results['thoughts_lines']
        all_results['blocked_lines'] += results['blocked_lines']
        all_results['blocked_details'].extend(results['blocked_details'])
        all_results['errors'].extend(results['errors'])
        all_results['structure_violations'].extend(results['structure_violations'])
        all_results['error_lines'].extend(results['error_lines'])
        
        if len(args.jsonl_files) > 1:
            file_name = Path(jsonl_file).name
            print(f"{file_name}: {results['total_lines']} 行, 有効 {results['valid_lines']}, 無効 {results['invalid_lines']}, 思考 {results['thoughts_lines']}, ブロック {results['blocked_lines']}")
    
    results = all_results
    
    # 結果の表示
    print()
    print(f"ファイル数: {len(args.jsonl_files)}")
    print(f"総行数: {results['total_lines']}")
    print(f"有効な行数: {results['valid_lines']}")
    print(f"無効な行数: {results['invalid_lines']}")
    print(f"思考トークンありの行数: {results['thoughts_lines']}")
    print(f"ブロックされた行数: {results['blocked_lines']}")
    print()
    
    # エラー詳細とブロック詳細を表示
    print_errors_and_violations(results, False)
    print_blocked_details(results)
    
    # 成功率の計算
    if results['total_lines'] > 0:
        success_rate = (results['valid_lines'] / results['total_lines']) * 100
        print(f"構造適合率: {success_rate:.2f}%")
    
    # 終了コード
    sys.exit(0 if results['invalid_lines'] == 0 else 1)


if __name__ == "__main__":
    main()
