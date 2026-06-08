"""텍스트 처리 유틸리티 — Kiwi 형태소 분석기 기반 문장 분할"""

from typing import List
from kiwipiepy import Kiwi

# Kiwi 인스턴스 캐시
_kiwi_instance: Kiwi | None = None


def get_kiwi_instance() -> Kiwi:
    """
    조선어 커스텀 사전이 적용된 Kiwi 인스턴스를 반환합니다.
    인스턴스는 캐시되어 재사용됩니다.
    """
    global _kiwi_instance
    
    if _kiwi_instance is not None:
        return _kiwi_instance
    
    # Kiwi 인스턴스 생성
    kiwi = Kiwi()
    
    # 조선어 고유 용어 사전 추가
    _add_choson_custom_words(kiwi)
    
    _kiwi_instance = kiwi
    return kiwi


def _add_choson_custom_words(kiwi: Kiwi) -> None:
    """
    조선어 고유 용어를 사전에 추가합니다.
    
    조선어 고유 용어:
    - 조선로동당 (×조선노동당)
    - 로동 (×노동)
    - 력사 (×역사)
    - 인민반장
    - 도당위원장
    - 내각총리
    - 륙군 (×육군)
    - 려단 (×여단)
    - 료하다 (×요하다)
    - 루군 (×유군)
    """
    custom_words = [
        "조선로동당",  # 조선노동당 아님
        "로동",        # 노동 아님
        "력사",        # 역사 아님
        "인민반장",
        "도당위원장",
        "내각총리",
        "륙군",        # 육군 아님
        "려단",        # 여단 아님
        "료하다",      # 요하다 아님
        "루군",        # 유군 아님
    ]
    
    for word in custom_words:
        try:
            kiwi.add_user_word(word, tag="NNP")  # 고유명사
        except Exception as e:
            # 이미 존재하는 단어라면 무시
            pass


def split_choson_sentences(text: str) -> List[str]:
    """
    조선어 종결어미 패턴 기반으로 문장을 분할합니다.
    
    조선어 종결어미 패턴:
    - 다$ (평서문)
    - 합니다$ (정중체)
    - 하였다$ (과거 평서문)
    - 한다$ (구어체)
    - 하자$ (청유형)
    - 합시다$ (정중 청유형)
    - 것이다$ (사실 강조)
    - 바이다$ (정의형)
    
    Args:
        text: 전체 텍스트
        
    Returns:
        List[str]: 분할된 문장 목록
    """
    import re
    
    # 종결어미 패턴
    # 조선어 텍스트는 마침표 뒤 공백이 없는 경우가 흔하므로
    # 마침표 유무와 관계없이, 공백/콜론/문자열끝/대문자(영어) 앞에서 분할
    #
    # 핵심: 단독 "다"는 문장 중간에도 흔히 등장하므로(예: "들은 다 같이")
    # 반드시 마침표가 있는 경우만 "다" 종결어미로 인식.
    # 나머지 종결어미(한다, 하였다, 합니다 등)는 혼동 가능성이 낮아
    # 마침표 없이도 분할.
    
    # 1단계: 마침표+뒤문장 패턴으로 명확한 문장 경계 분할
    # "다.다음" / "한다.그" / "하였다.그" 등 마침표 뒤 공백 없어도 분할
    dot_patterns = [
        r"(?<=다\.)(?=[^\s])",          # "다." + 비공백(공백 없는 경우)
        r"(?<=다\.)\s+",                 # "다." + 공백(공백 있는 경우, 공백 소모)
        r"(?<=하였다\.)(?=[^\s])",
        r"(?<=하였다\.)\s+",
        r"(?<=합니다\.)(?=[^\s])",
        r"(?<=합니다\.)\s+",
        r"(?<=했습니다\.)(?=[^\s])",
        r"(?<=했습니다\.)\s+",
        r"(?<=하였습니다\.)(?=[^\s])",
        r"(?<=하였습니다\.)\s+",
        r"(?<=한다\.)(?=[^\s])",
        r"(?<=한다\.)\s+",
        r"(?<=하자\.)(?=[^\s])",
        r"(?<=하자\.)\s+",
        r"(?<=합시다\.)(?=[^\s])",
        r"(?<=합시다\.)\s+",
        r"(?<=것이다\.)(?=[^\s])",
        r"(?<=것이다\.)\s+",
        r"(?<=바이다\.)(?=[^\s])",
        r"(?<=바이다\.)\s+",
    ]
    
    # 2단계: 마침표 없는 종결어미 (단독 "다"는 제외 — 오분석 위험)
    no_dot_patterns = [
        r"(?<=하였다)(?=[\s])",
        r"(?<=합니다)(?=[\s])",
        r"(?<=했습니다)(?=[\s])",
        r"(?<=하였습니다)(?=[\s])",
        r"(?<=한다)(?=[\s])",
        r"(?<=하자)(?=[\s])",
        r"(?<=합시다)(?=[\s])",
        r"(?<=것이다)(?=[\s])",
        r"(?<=바이다)(?=[\s])",
    ]
    
    combined_pattern = "|".join(dot_patterns + no_dot_patterns)
    
    # 룩어라운드 패턴은 문자열을 소모하지 않고 분할 위치만 지정
    sentences = re.split(combined_pattern, text)
    
    # 빈 문장 제거 및 트림
    sentences = [s.strip() for s in sentences if s.strip()]
    
    return sentences