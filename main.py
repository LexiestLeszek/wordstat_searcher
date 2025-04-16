import time
import json
import requests
import re
from together import Together

together_client = Together(api_key='LLM_API_KEY')

def ask_llm(user_prompt, system_prompt):
    response = together_client.chat.completions.create(
        model="deepseek-ai/DeepSeek-V3",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=1.1
    )
    return response.choices[0].message.content

def generate_initial_keywords(product_description):
    """
    Use an LLM to generate potential search queries based on product description.
    """
    system_prompt = """
    Вы эксперт по исследованию ключевых слов для поисковой системы Yandex в России.
    Генерируйте потенциальные поисковые запросы, которые пользователи могут использовать при поиске описанного продукта.
    Сфокусируйтесь на проблемно-ориентированных ключевых словах, отражающих потребности и болевые точки пользователей.
    Возвращайте только Python-список строк с этими поисковыми запросами.
    """

    user_prompt = f"""
    Сгенерируйте 15 потенциальных поисковых запросов для этого продукта: "{product_description}"
    Сфокусируйтесь на проблемах, которые может решать продукт, и том, как российские пользователи искали бы такие решения.
    Включите сочетание общих и специфичных терминов.
    Верни только список ключевых слов в формате: ["ключевое слово 1", "ключевое слово 2", "ключевое слово 3"]
    """
    
    response = ask_llm(user_prompt, system_prompt)
    
    # Parse the response to extract keywords
    try:
        # Try to evaluate as a Python list
        keywords = eval(response)
        if isinstance(keywords, list):
            return keywords
    except:
        # If evaluation fails, try to extract using regex
        pattern = r'["\'](.*?)["\']'
        matches = re.findall(pattern, response)
        if matches:
            return matches
        
        # Alternative: extract lines that might be keywords
        lines = response.strip().split('\n')
        keywords = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('//'):
                # Remove list markers and quotes
                cleaned = re.sub(r'^[-*•"\']|\s[-*•"\']\s|["\'"]$', '', line).strip()
                if cleaned:
                    keywords.append(cleaned)
        return keywords

def query_wordstat_api(keywords, token, username, exclude=None, region=None):
    """
    Query Yandex Wordstat API to get search volumes for keywords.
    """
    # API URL for Yandex Direct
    url = 'https://api.direct.yandex.ru/v4/json/'
    
    # Prepare request data
    data = {
        "method": "CreateNewWordstatReport",
        "param": {
            "Phrases": keywords,
            "GeoID": region or []
        },
        "token": token
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Create a new Wordstat report
    response = requests.post(url, json=data, headers=headers)
    result = response.json()
    
    if 'data' not in result:
        error_msg = result.get('error_str', 'Unknown error')
        raise Exception(f"Failed to create report: {error_msg}")
    
    report_id = result['data']
    print(f"Created Wordstat report ID: {report_id}")
    
    # Check report status until it's ready
    status = "Processing"
    while status != "Done":
        time.sleep(3)  # Don't query too frequently
        
        check_data = {
            "method": "GetWordstatReportList",
            "param": {},
            "token": token
        }
        
        response = requests.post(url, json=check_data, headers=headers)
        report_list = response.json()
        
        if 'data' not in report_list:
            raise Exception("Failed to get report list")
        
        for report in report_list['data']:
            if report['ReportID'] == report_id:
                status = report['StatusReport']
                if status == "Done":
                    print("Report is ready")
                    break
                elif status == "Failed":
                    raise Exception("Report creation failed")
                else:
                    print(f"Report status: {status}")
    
    # Get the report data
    get_data = {
        "method": "GetWordstatReport",
        "param": report_id,
        "token": token
    }
    
    response = requests.post(url, json=get_data, headers=headers)
    report_data = response.json()
    
    if 'data' not in report_data:
        raise Exception("Failed to get report data")
    
    # Extract search volumes from the report
    keyword_volumes = {}
    for item in report_data['data']:
        keyword = item['Phrase']
        volume = int(item['Shows'])
        keyword_volumes[keyword] = volume
    
    # Clean up by deleting the report
    delete_data = {
        "method": "DeleteWordstatReport",
        "param": report_id,
        "token": token
    }
    
    requests.post(url, json=delete_data, headers=headers)
    
    return keyword_volumes

def expand_keywords_with_llm(current_results, product_description):
    """
    Generate additional keywords based on current results.
    """
    system_prompt = """
    Вы эксперт по исследованию ключевых слов для поисковой системы Yandex в России.
    Проанализируйте текущие результаты по ключевым словам и предложите дополнительные поисковые запросы для изучения.
    Сфокусируйтесь на выявлении пробелов в текущем списке ключевых слов и предложении новых проблемно-ориентированных терминов.
    Возвращайте только Python-список дополнительных поисковых запросов.
    """

    user_prompt = f"""
    На основе этого описания продукта: "{product_description}"

    И текущих результатов по ключевым словам:
    {json.dumps(current_results, ensure_ascii=False, indent=2)}

    Сгенерируйте 10 дополнительных поисковых запросов, которые:
    1. Ещё отсутствуют в текущем списке
    2. Охватывают различные потребности или проблемы пользователей
    3. Используют разные формулировки и терминологию

    Верни только Python список новых поисковых запросов без пояснений вот в таком формате: ["ключевое слово 1", "ключевое слово 2", "ключевое слово 3"]
    """
    
    response = ask_llm(user_prompt, system_prompt)
    
    # Parse the response with the same logic as in generate_initial_keywords
    try:
        keywords = eval(response)
        if isinstance(keywords, list):
            return keywords
    except:
        pattern = r'["\'](.*?)["\']'
        matches = re.findall(pattern, response)
        if matches:
            return matches
        
        lines = response.strip().split('\n')
        keywords = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('//'):
                cleaned = re.sub(r'^[-*•"\']|\s[-*•"\']\s|["\'"]$', '', line).strip()
                if cleaned:
                    keywords.append(cleaned)
        return keywords

def find_top_search_terms(product_description, token, username, iterations=3, max_results=20):
    """
    Main function to find the most searched terms for a product.
    
    Args:
        product_description: Description of the product
        token: Yandex Direct API token
        username: Yandex username
        iterations: Number of LLM-API query cycles to run
        max_results: Maximum number of keywords to return
        
    Returns:
        Dictionary of keywords to monthly search volumes
    """
    all_results = {}
    
    # Step 1: Generate initial keywords using LLM
    print(f"Generating initial keywords for: {product_description}")
    initial_keywords = generate_initial_keywords(product_description)
    print(f"Generated {len(initial_keywords)} initial keywords")
    
    # Step 2: Get search volumes for initial keywords
    print("Querying Yandex Wordstat for initial keywords...")
    initial_results = query_wordstat_api(initial_keywords, token, username)
    all_results.update(initial_results)
    print(f"Found {len(initial_results)} keywords with search volume")
    
    # Step 3: Iteratively expand keywords
    for i in range(iterations - 1):
        print(f"\nStarting iteration {i+2}/{iterations}")
        
        # Generate new keywords based on current results
        new_keywords = expand_keywords_with_llm(all_results, product_description)
        print(f"Generated {len(new_keywords)} additional keywords")
        
        # Filter out keywords we've already checked
        new_keywords = [k for k in new_keywords if k not in all_results]
        if not new_keywords:
            print("No new keywords to check")
            break
            
        print(f"Querying Yandex Wordstat for {len(new_keywords)} new keywords...")
        new_results = query_wordstat_api(new_keywords, token, username)
        all_results.update(new_results)
        print(f"Found {len(new_results)} additional keywords with search volume")
    
    # Step 4: Sort by search volume and return top results
    sorted_results = dict(sorted(all_results.items(), key=lambda x: x[1], reverse=True)[:max_results])
    
    return sorted_results

# Example usage
if __name__ == "__main__":
    # Set your Yandex API credentials
    YANDEX_API_TOKEN = "your_api_token" 
    YANDEX_USERNAME = "your_username"
    
    # Set your product description
    product_description = "ai dating app assistant in telegram"
    
    # Find the top search terms
    top_keywords = find_top_search_terms(
        product_description,
        YANDEX_API_TOKEN,
        YANDEX_USERNAME,
        iterations=3,
        max_results=20
    )
    
    # Display results
    print("\nTop searched terms for your product:")
    print("-" * 50)
    for keyword, volume in top_keywords.items():
        print(f"{keyword}: {volume} monthly searches")
