# encoding:utf-8
import json
import random

import requests

from bot.aideas.aideas_session import AideasSession
from bot.bot import Bot
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf, load_config


class AideasBot(Bot):
    def __init__(self):
        super().__init__()
        self.aideas_api = conf().get("aideas_api")
        self.sessions = SessionManager(AideasSession, model=conf().get("aideas_model") or "gpt-3.5-turbo")

    def reply(self, query, context=None):
        # acquire reply content
        if context.type == ContextType.TEXT:
            logger.info("[Aideas] query={}".format(query))

            session_id = context["session_id"]
            reply = None
            clear_memory_commands = conf().get("clear_memory_commands", ["#清除记忆"])
            if query in clear_memory_commands:
                self.sessions.clear_session(session_id)
                reply = Reply(ReplyType.INFO, "记忆已清除")
            elif query == "#清除所有":
                self.sessions.clear_all_session()
                reply = Reply(ReplyType.INFO, "所有人记忆已清除")
            elif query == "#更新配置":
                load_config()
                reply = Reply(ReplyType.INFO, "配置已更新")
            if reply:
                return reply
            session = self.sessions.session_query(query, session_id)
            logger.debug("[Aideas] session query={}".format(session.messages))

            reply_content = self.reply_text(session)
            logger.debug(
                "[CHATGPT] new_query={}, session_id={}, reply_cont={}".format(
                    session.messages,
                    session_id,
                    reply_content["content"],
                )
            )
            self.sessions.session_reply(reply_content["content"], session_id, reply_content.get("total_tokens", 1))
            reply = Reply(ReplyType.TEXT, reply_content["content"])
            return reply
        else:
            reply = Reply(ReplyType.ERROR, "Bot不支持处理{}类型的消息".format(context.type))
            return reply

    def reply_text(self, session: AideasSession, retry_count=0) -> dict:
        """
         call aideas api to get the answer
        :param session: a conversation session
        :param retry_count: retry count
        :return: {}
        """
        try:
            response = requests.post(url=self.aideas_api, json=self.format_aideas_params(session))
            result = json.loads(response.text)
            if result.get("code") != 200:
                raise RuntimeError("请求Aideas失败, response: {}".format(response.text))
            return {
                "content": result["answer"]["content"],
            }
        except Exception as e:
            logger.error(e)
            need_retry = retry_count < 2
            result = {"completion_tokens": 0, "content": "我现在有点累了，等会再来吧"}
            if need_retry:
                logger.warn("[Aideas] 第{}次重试".format(retry_count + 1))
                return self.reply_text(session, retry_count + 1)
            else:
                return result

    def format_aideas_params(self, session: AideasSession):
        params = {
            "id": random.randint(0, 2147483647),
            "question": session.messages[len(session.messages) - 1].get("content"),
            "sessionId": session.session_id
        }
        """
        上下文格式转换为：
        [{
                "question": "xxx",
                "answer": "xxx"
            }
        ]
        """
        context = []
        index = 0
        while True:
            if index >= len(session.messages) - 2:
                break
            # 上下文为一问一答的形式，如果不是此格式就舍弃
            if session.messages[index].get("role") == "user" and session.messages[index + 1].get("role") == "assistant":
                context.append({
                    "question": session.messages[index].get("content"),
                    "answer": session.messages[index].get("content")
                })
                index += 2
            else:
                index += 1
        params['context'] = context
        return params





