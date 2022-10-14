from base64 import b64decode
import copy
from math import ceil
from typing import Any, cast

from algosdk.account import address_from_private_key
from algosdk.atomic_transaction_composer import (
    TransactionSigner,
    AccountTransactionSigner,
    MultisigTransactionSigner,
    LogicSigTransactionSigner,
    AtomicTransactionComposer,
    ABI_RETURN_HASH,
    TransactionWithSigner,
    abi,
)
from algosdk.future import transaction
from algosdk.logic import get_application_address
from algosdk.source_map import SourceMap
from algosdk.v2client.algod import AlgodClient
from algosdk.constants import APP_PAGE_MAX_SIZE

from beaker.application import Application, get_method_spec
from beaker.decorators import (
    HandlerFunc,
    MethodHints,
    DefaultArgument,
    DefaultArgumentClass,
)
from beaker.client.state_decode import decode_state
from beaker.client.logic_error import LogicException
from beaker.client.application_client import ApplicationClient
import algosdk
from config import player
from algorand import sp

def get_transaction(atc: AtomicTransactionComposer, i: int):
    tws: TransactionWithSigner = atc.build_group()[i]
    txn = tws.txn.dictify()
    if "grp" in txn: del txn["grp"]
    tws.txn = transaction.Transaction.undictify(txn)
    return tws

def remove_group(tws: TransactionWithSigner):
    txn = tws.txn.dictify()
    if "grp" in txn: del txn["grp"]
    tws.txn = transaction.Transaction.undictify(txn)
    return tws

def finalize(appclient: ApplicationClient, atc: AtomicTransactionComposer):
    try:
        opt_in_result = atc.execute(appclient.client, 4)
    except Exception as e:
        if "logic" in str(e):
            raise appclient.wrap_approval_exception(e)
        else:
            raise e

    return opt_in_result.tx_ids[0]

def create_atc_from_kwargs(kwargs):
    atc = AtomicTransactionComposer()
    for k,arg in kwargs.items():
        if type(arg) == AtomicTransactionComposer:
            txns = arg.build_group()
            for i in range(0, len(txns)-1):
                atc.add_transaction(remove_group(txns[i]))
            kwargs[k] = remove_group(txns[-1])
    return atc  

def create_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
    extra_pages: int = None,
    **kwargs,
) -> tuple[int, str, str]:
    """Submits a signed ApplicationCallTransaction with application id == 0 and the schema and source from the Application passed"""

    appclient.build()
    assert appclient.clear_binary is not None and appclient.approval_binary is not None

    if extra_pages is None:
        extra_pages = ceil(
            (
                (len(appclient.approval_binary) + len(appclient.clear_binary))
                - APP_PAGE_MAX_SIZE
            )
            / APP_PAGE_MAX_SIZE
        )

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_create is not None:
        appclient.add_method_call(
            atc,
            appclient.app.on_create,
            sender=sender,
            suggested_params=sp,
            on_complete=on_complete,
            approval_program=appclient.approval_binary,
            clear_program=appclient.clear_binary,
            global_schema=appclient.app.app_state.schema(),
            local_schema=appclient.app.acct_state.schema(),
            extra_pages=extra_pages,
            app_args=args,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCreateTxn(
                    sender=sender,
                    sp=sp,
                    on_complete=on_complete,
                    approval_program=appclient.approval_binary,
                    clear_program=appclient.clear_binary,
                    global_schema=appclient.app.app_state.schema(),
                    local_schema=appclient.app.acct_state.schema(),
                    extra_pages=extra_pages,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def update_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    **kwargs,
) -> str:

    """Submits a signed ApplicationCallTransaction with OnComplete set to UpdateApplication and source from the Application passed"""
    appclient.build()

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_update is not None:
        appclient.add_method_call(
            atc,
            appclient.app.on_update,
            on_complete=transaction.OnComplete.UpdateApplicationOC,
            sender=sender,
            suggested_params=sp,
            index=appclient.app_id,
            approval_program=appclient.approval_binary,
            clear_program=appclient.clear_binary,
            app_args=args,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationUpdateTxn(
                    sender=sender,
                    sp=sp,
                    index=appclient.app_id,
                    approval_program=appclient.approval_binary,
                    clear_program=appclient.clear_binary,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def opt_in_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    **kwargs,
) -> str:
    """Submits a signed ApplicationCallTransaction with OnComplete set to OptIn"""

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_opt_in is not None:
        appclient.add_method_call(
            atc,
            appclient.app.on_opt_in,
            on_complete=transaction.OnComplete.OptInOC,
            sender=sender,
            suggested_params=sp,
            index=appclient.app_id,
            app_args=args,
            signer=signer,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationOptInTxn(
                    sender=sender,
                    sp=sp,
                    index=appclient.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def close_out_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    **kwargs,
) -> str:
    """Submits a signed ApplicationCallTransaction with OnComplete set to CloseOut"""

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_close_out is not None:
        appclient.add_method_call(
            atc,
            appclient.app.on_close_out,
            on_complete=transaction.OnComplete.CloseOutOC,
            sender=sender,
            suggested_params=sp,
            index=appclient.app_id,
            app_args=args,
            signer=signer,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationCloseOutTxn(
                    sender=sender,
                    sp=sp,
                    index=appclient.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def clear_state_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    **kwargs,
) -> str:

    """Submits a signed ApplicationCallTransaction with OnComplete set to ClearState"""

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_clear_state is not None:
        appclient.add_method_call(
            atc,
            appclient.app.on_clear_state,
            on_complete=transaction.OnComplete.ClearStateOC,
            sender=sender,
            suggested_params=sp,
            index=appclient.app_id,
            app_args=args,
            signer=signer,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationClearStateTxn(
                    sender=sender,
                    sp=sp,
                    index=appclient.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def delete_nosend(
    appclient: ApplicationClient,
    sender: str = None,
    signer: TransactionSigner = None,
    args: list[Any] = None,
    suggested_params: transaction.SuggestedParams = None,
    **kwargs,
) -> str:
    """Submits a signed ApplicationCallTransaction with OnComplete set to DeleteApplication"""

    sp = appclient.get_suggested_params(suggested_params)
    signer = appclient.get_signer(signer)
    sender = appclient.get_sender(sender, signer)

    atc = create_atc_from_kwargs(kwargs)
    if appclient.app.on_delete:
        appclient.add_method_call(
            atc,
            appclient.app.on_delete,
            on_complete=transaction.OnComplete.DeleteApplicationOC,
            sender=sender,
            sp=sp,
            index=appclient.app_id,
            app_args=args,
            signer=signer,
            **kwargs,
        )
    else:
        atc.add_transaction(
            TransactionWithSigner(
                txn=transaction.ApplicationDeleteTxn(
                    sender=sender,
                    sp=sp,
                    index=appclient.app_id,
                    app_args=args,
                    **kwargs,
                ),
                signer=signer,
            )
        )

    return atc

def call_nosend(
    appclient: ApplicationClient,
    method: abi.Method | HandlerFunc,
    sender: str = None,
    signer: TransactionSigner = None,
    suggested_params: transaction.SuggestedParams = None,
    on_complete: transaction.OnComplete = transaction.OnComplete.NoOpOC,
    local_schema: transaction.StateSchema = None,
    global_schema: transaction.StateSchema = None,
    approval_program: bytes = None,
    clear_program: bytes = None,
    extra_pages: int = None,
    accounts: list[str] = None,
    foreign_apps: list[int] = None,
    foreign_assets: list[int] = None,
    note: bytes = None,
    lease: bytes = None,
    rekey_to: str = None,
    **kwargs,
) -> AtomicTransactionComposer:

    """Handles calling the application"""

    if not isinstance(method, abi.Method):
        method = get_method_spec(method)

    hints = appclient.method_hints(method.name)

    atc = create_atc_from_kwargs(kwargs)
    
    atc = appclient.add_method_call(
        atc,
        method,
        sender,
        signer,
        suggested_params=suggested_params,
        on_complete=on_complete,
        local_schema=local_schema,
        global_schema=global_schema,
        approval_program=approval_program,
        clear_program=clear_program,
        extra_pages=extra_pages,
        accounts=accounts,
        foreign_apps=foreign_apps,
        foreign_assets=foreign_assets,
        note=note,
        lease=lease,
        rekey_to=rekey_to,
        **kwargs,
    )
    # If its a read-only method, use dryrun (TODO: swap with simulate later?)
    if hints.read_only:
        dr_req = transaction.create_dryrun(appclient.client, atc.gather_signatures())
        dr_result = appclient.client.dryrun(dr_req)
        method_results = appclient._parse_result(
            {0: method}, dr_result["txns"], atc.tx_ids
        )
        return method_results.pop()

    return atc
