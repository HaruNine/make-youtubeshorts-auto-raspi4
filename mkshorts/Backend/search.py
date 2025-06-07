import requests

from typing import List
from termcolor import colored

def search_for_stock_videos(query: str, api_key: str, it: int, min_dur: int) -> List[str]:
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page={it}"
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(colored(f"[-] Pexels API error: {r.status_code}", "red"))
        return []
    response = r.json()
    video_urls = []
    try:
        for video in response.get("videos", []):
            if video.get("duration", 0) < min_dur:
                continue
            best_url = ""
            best_res = 0
            for file in video.get("video_files", []):
                if file.get("file_type") == "video/mp4":
                    res = file.get("width", 0) * file.get("height", 0)
                    if res > best_res:
                        best_res = res
                        best_url = file.get("link")
            if best_url:
                video_urls.append(best_url)
    except Exception as e:
        print(colored("[-] No Videos found.", "red"))
        print(colored(e, "red"))
    print(colored(f"\t=> \"{query}\" found {len(video_urls)} Videos", "cyan"))
    return video_urls