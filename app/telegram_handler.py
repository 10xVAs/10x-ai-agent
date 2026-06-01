typing_task = asyncio.create_task(keep_typing())
    try:
        reply = await chat(user_id=user_id, user_message=text)
        typing_task.cancel()
        await send_typing(chat_id)
        await send_message(chat_id, reply)
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        err_str = str(e).lower()
        if "rate_limit" in err_str or "429" in err_str:
            await send_message(
                chat_id,
                "⏳ I'm processing requests faster than my current API tier allows. "
                "Give me 30-60 seconds and try again.",
            )
        elif "overloaded" in err_str or "529" in err_str:
            await send_message(
                chat_id,
                "⚠️ Claude's servers are temporarily overloaded. Try again in a moment.",
            )
        else:
            await send_message(
                chat_id,
                "⚠️ Something went wrong on my end. Try again, or use /new to reset.",
            )
    finally:
        typing_task.cancel()