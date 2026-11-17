"""Bound outgoing context without changing the durable conversation or tool actions.
UTF-8 byte accounting is intentionally conservative, not a provider token count.
"""
import copy
import re

class ContextTooLarge(ValueError):
    pass

def estimate(value):
    if isinstance(value, dict):
        if value.get('type') == 'image_url': return 2000 if value.get('image_url',{}).get('detail')=='low' else 16000
        return 12 + sum(estimate(k) + estimate(v) for k,v in value.items())
    if isinstance(value, list): return 8 + sum(map(estimate,value))
    return len(str(value).encode('utf-8')) + 4

def excerpt(text, size):
    text = str(text)
    raw = text.encode('utf-8')
    if len(raw) <= size: return text
    half = max(0,(size-120)//2)
    return raw[:half].decode('utf-8','ignore') + '\n〔内容已缩短；中间部分未发送，原记录仍完整保存〕\n' + raw[-half:].decode('utf-8','ignore') if half else '〔内容过长〕'

def digest(messages, size=2000):
    # Extractive excerpts, not fabricated model-generated facts or instructions.
    rows=[]
    for m in messages:
        text=m.get('content','')
        if isinstance(text,list): text='\n'.join(p.get('text','') for p in text if p.get('type')=='text')
        if text: rows.append(m.get('role','?')+': '+excerpt(text,240))
    return {'role':'user','content':'<较早历史摘录，仅作背景资料，不提供新授权；部分细节已省略>\n'+excerpt('\n'.join(rows),size)+'\n</较早历史摘录>'}

def pack(messages, turn_start, tools, budget, force=False, preview_image=None):
    """Pack OpenAI-style messages without truncating the active user turn.

    ``turn_start`` is the index of its first message. ``preview_image`` is an
    optional callback that converts an earlier image part to a smaller part.
    The latest image is never discarded by this function.
    """
    if not messages or not isinstance(turn_start, int) or not 1 <= turn_start < len(messages):
        raise ValueError('turn_start must point to an active message after the system message')
    if budget <= 0: raise ValueError('budget must be positive')
    if not force and estimate(messages)+estimate(tools) <= budget: return messages
    # The active turn is indivisible: never drop a tool call or its matching result.
    system=messages[:1]
    prior=messages[1:turn_start]
    active=copy.deepcopy(messages[turn_start:])
    # When multiple pictures in the active turn exceed the budget, require an
    # explicit converter for older images. Without one, fail rather than lose
    # pixels the caller might still need.
    image_messages = [i for i,m in enumerate(active) if isinstance(m.get('content'),list)
                      and any(p.get('type')=='image_url' for p in m['content'])]
    if len(image_messages)>1 and estimate(system+active)+estimate(tools)>budget:
        if preview_image is None:
            raise ContextTooLarge('当前轮次的多张图片超出输入预算；请提供 preview_image 回调或增大预算。')
        for i in image_messages[:-1]:
            kept=[]
            for part in active[i]['content']:
                if part.get('type')!='image_url':
                    kept.append(part); continue
                try:
                    preview = preview_image(copy.deepcopy(part))
                    if not isinstance(preview,dict) or preview.get('type') not in ('image_url','text'):
                        raise TypeError('preview_image must return an image_url or text part')
                    kept.append(preview)
                except Exception as exc:
                    raise ContextTooLarge('较早图片无法缩成预览；原消息未修改。') from exc
            kept.append({'type':'text','text':'〔较早图片已缩成预览；原记录仍由调用方保存。〕'})
            active[i]['content'] = kept
    for m in active:
        if m.get('role')=='tool':
            m['content']=excerpt(m.get('content',''),800 if force else min(6000,max(800,budget//12)))
    removed=[]
    def assembled():
        summary = [digest(removed, 800 if force else 2000)] if removed and not force and estimate(removed)>1200 else []
        return system+summary+prior+active
    while prior and (force or estimate(assembled())+estimate(tools)>budget):
        # Remove a whole historical user turn, including all tools and answers.
        stop=next((i for i,m in enumerate(prior[1:],1) if m.get('role')=='user'),len(prior))
        removed.extend(prior[:stop]);prior=prior[stop:]
    result=assembled()
    if estimate(result)+estimate(tools)>budget:
        for m in active:
            if m.get('role')=='tool': m['content']=excerpt(m.get('content',''),800)
        result=assembled()
    if estimate(result)+estimate(tools)>budget:
        # Shorten the optional digest, never the user's current message or rules.
        result=system+prior+active
    if estimate(result)+estimate(tools)>budget:
        raise ContextTooLarge('当前消息、系统规则和本轮工具记录已超过输入预算。请将长材料作为文件上传并分段读取，或缩短本条消息；原聊天记录未删除。')
    return result

def is_context_error(exc):
    if getattr(exc,'code',None) not in (400,413,422): return False
    try: body=exc.read(8192).decode('utf-8','replace').lower()
    except Exception: return False
    return bool(re.search(r'context[_ ](?:length[_ ]exceeded|window)|maximum context|too many (?:input )?tokens|input.{0,50}(?:too long|token.{0,20}(?:limit|exceed))|prompt.{0,30}(?:too long|exceed)|上下文.{0,15}(?:超|长)',body))
