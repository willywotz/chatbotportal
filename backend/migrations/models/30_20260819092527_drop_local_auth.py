from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    # Keycloak owns identity now: drop the local user/session/API-key tables.
    # CASCADE removes the FK constraints on conversations.user_id / messages.user_id
    # (and sessions/user_api_keys own FKs); those columns stay as plain UUIDs (the
    # Keycloak subject id). The aerich-generated CREATE/ALTER noise for
    # domain_events/rate_limit_counters was removed — those already exist (migration 29).
    return """
        DROP TABLE IF EXISTS "sessions" CASCADE;
        DROP TABLE IF EXISTS "user_api_keys" CASCADE;
        DROP TABLE IF EXISTS "users" CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    # Irreversible: the dropped tables and their data are gone.
    return ""


MODELS_STATE = (
    "eJztXWtv47YS/SuCP22BNEicx6a5D8DOerdpk01uNrm3aF0oskTbaiRRpahk02L/+x3qZT"
    "0oxbQtW7IJLLKJxKPHITWcGc4M/+7Y2ECWt9+bIEd/7Zwrf3cczUbwS+7MntLRXHd2nB2g"
    "2sgKmmqsjYmCg9rIo0TTKRwfa5aH4JCBPJ2YLjWxw1p/ws+IODZyqBIAX5XgkvsMbWAd4K"
    "YzqWo4dK5NQjDxFDpFymN890cleCBlTLAdnMHEnJiOZilffFcbaR5SPH2KbC24k++Yf/pI"
    "pXiCoC2B+/32Oxw2HQN9hTeJ/nSf1LGJLCPDjGmwCwTHVfrqBsceHi4/fAxasrcYqTq2fN"
    "uZtXZf6RQ7SXPfN419hmHn4PkR0SgyUpw5vmVF9MaHwieGA5T4KHlUY3bAQGPNtxjznX+O"
    "fUdnhCvQa/s+NaEn49uo7Ob/7hQ6ht0y1wXRIR07rFNNhzJi/v4WvuKMgOBoh9334sfe3b"
    "uj0++CV8YenZDgZEBP51sA1KgWQgOSZ6wG/xd4vZhqhM9r3D7HLDzoIpzGB2akzkZvzGpM"
    "0GKsdWztq2ohZ0Kn8Gf35KSCxv/27gImoVVAJYYvKvzUPkenuuE5RumMQm+KCVVFicyiFq"
    "IzGoAbY/PkYA4yTw5KuWSnslRaeIJFSIzbt5K+WgZj+skKRN6jr5RPZA7WEj4r6Lsf/HLP"
    "ntn2vD+tNGvvrnu/BITar9GZq5vPn+LmKZYvrm76OXLh9g4KBHxIDXekDhzfDki+hGfVHB"
    "0VyOZcZn3itNO7vSzOQp3ri9tzBX4MHTh/rsAP+K3bg9+6vbyKMM/gPpxHNhyWy4bDgmwA"
    "MqnvLcr5DL1GqkEhM58Rh22DaGN6rgT/DZ2w2bkS/j90bMYpcth7nCupP4aOYXrsgQyARr"
    "8t0jfdefqmW9433ULfaD7FaupJi73Ux9hCmsOXPjx4rptGgK+rn/ga8yqkUP/m5iojhfqX"
    "eTHzcN0fwJcQkA2NTBocvvx8zxn+ngqKHaKqRosEfwBSqGmjEm2jgM7xa0Tw/fiX1gn8y+"
    "vBl/ve9W2G7w+9+wE7081I/Pjou9PcGE8uovzv8v5Hhf2p/HrzeZBXrJN297922DMFA9jB"
    "L6pmpF87Phwfys7UTCX3dMybR376cvO5ZKLOoHKd+OAAn78Zpk73FMv06O+1SbaZpTPyTY"
    "uajrfPbliTfcPoqJ7M8/N2rr/YBYqTuYWJiLKZAFqiHdWtrCPHcDHcTPWJJcJjHtdKOg8P"
    "DubTcA6qdJwD3kw6VW0EjHDcHeWc5mCtpHT1IzRgZYo0Awl96DlYK8k8nHd4Vo3OPJ/Mm6"
    "e6GtxAgM0MqJVc1mKoa66pPqFXYb9RHtdKRmsZnQTBy3hUHWNi8zTkck6LyFayWoMAhcEW"
    "T9cc07tcTS0Apaa6uKYKp1x4AqSGCyki/cCByp5YvCfYsPZcpKtEexFxr+ZxLREv6/avoq"
    "/AEbw/qAuvFtY4GnD5SOdhVzDUG0V6bWM6VHaFJXwKtiGqt0GouMTExKSvRfYvnRJ5kobk"
    "mIe3aOSwhieC/77vHh6/Pz47Oj0+gybBoyRH3lcQX/SHEuxTRNRp9L7zSuIcbI2LAfWMyF"
    "rksGF6YLDpU5U5goEwlSMZSscmH7yjo9TWXZVibAmbeQVgS1SGNVjOcMfAUHN0pBLkYsIR"
    "AOXzFh8tNYU5JiqKqWapumZZIvIgh1pIECwkcQ+aIwbg1eB2qu8K8JbB7DJrBn7hxLK8xV"
    "uM2knmdILYyy2wUJxFrmCReBMxf/AOxo1jvUZSuSWrxtEEUrlo7LvGgh2bRcqO3WjHBg/P"
    "Ip3HT6moXHZgpOlPLxox1MwZbgiahSecebgfXeDjz3fI0koC+qIo84vkYld40mQVZ3Z01v"
    "MzTibYMpCjBj58uP6SpHwKrvaf6GLN/BDmosXFrm9pZFW83IaXEyCmQcOFfVq4i8s+tuIp"
    "u2vnj2iONgmemt2b3SnO1fANk7IPiJfHEZ/bq8zkYK2S7/nNXI5yOmR6RR3G1BLpFdCNmK"
    "hi3KYxSzDcKHv0TQrzlCFbM4WiinIw6S5J8clNBqikcpk8gE0ohjWvg+PRH6AnVQT984nM"
    "wVo5Jo/mIfOonMyjMjJ5QvFNKrlSsR1Enh7PQeTpcSmR7FQ+14dyhWRF9HCCkA7Pvbcdnt"
    "KNshXWduhGETC367QWsjY3x2QoGOXldgPHGSCNh60yHlqguXUo8ugS3NWtu82VtFm6Vri5"
    "RM2VGhYrz/irysYsT0FbdwZmszm04G0d/VW1RZZTs6CdXN0q03ur0ttL9F4Z8CMV3W1TdH"
    "k5ESNscOILK8Lkcri1Wdxt+mqS4HpxdnNASS+HXht5HthQgt7zLGoX/eeeZ7IiGFRdjMAy"
    "/C5SGdQ/E+UvDdoR0gq+lTyHRQI/YoLMifMzeg1oTBdu4a8/z0riNZW4wrLzHotGe0n8Jd"
    "mhAW8I74XCeh8XvS8XvQ+DzreNOaWeEfG06MV5PqnZ+b03XFJJyzkrE4LJSJU0Thn63YPD"
    "Y8VO1xvMXFis6GCmvGHtd5NutIa50ahJLSG3TwJYo7E49A9QV2M/D38Ifr6f/X7UZT+Pj4"
    "I2o+DnYXDkbIVut/n8blWOt4J/wyXo2URCiZIpSEsW+datFaervs677JfGyPTfxdcD2+H0"
    "7Hi+roPqvjLhsHrPZ2xZ6Njnpe+VOj8LuJ30fybug9ilNu9oLABbImNrr2T1lSIC+pzqwf"
    "hiqz1isSkl8FaSW0tlFhtRjalnInNWGtOkOYvdtk1zVmhjLuLazyJlvcgN14uUazRbukYj"
    "c7q2omML+Te+h0RD/1OQXfUcz5MEF5kBSyY0XYdXaeZnsZFMpg+YFeEePKPgdgUvcPr0Xp"
    "UT2Agaqoi1lFGJW+ZODXpVOJQui2pnBFgtttECpc5WW+FsZy0jqVBvhd5VVKjjClSLWb15"
    "sDR8N2D4NiRZY/CsWXfIC3ukoA+lzlaqQwjasb03oKHUhrZMG/J0TDiK0EeYoEvWMBJEjt"
    "wxgzRzrqig7sPNQ/9qoNzeDS4uv1xGs3QiPoKT7NBsZ5u7Qe8qv6TpeC+8Cv0V9XQThIzn"
    "5i0S/+EbE1beTvPEtoHL4yS7Mlp+hxTHXCEhQecdH73KKbRVjrxSWjmzpWgsaJtrNO3lgk"
    "L5w6ZJ0aGDr0j32daEfWKicYenCWdbVGvDcVt1xBpLjXjLNGK4CUViRblTEKlx8DSOlgSe"
    "4aclOM35Wk/ncbXmdYWUp/U072hN3ngBvS2PlZpbAzS3hviIcroIZ3YsaivlsyOvlqWcHb"
    "dndixXgsunxzSmLStn654hk+1/KHZNXSg6ngNt0rJa24LkpXdki+bYxmTDNkuEtSkdtsGu"
    "j6XyYTP5EPHS2uLRYNnFvPZwWmtA2JVl3xL8bBqB6lhQbNOnK7Vay7JVN2opVdotU2lFt7"
    "ZaakerBThdZQjY6nOPgu2xfSJU6zqNaYtBsIZ842hrbKGF5BlEeh656cY+nUb7fIqM0Bxs"
    "jdz24M6YmH8l031zQz8DkoLKEWI7wGdha+S2jzQSdmhDhWmy5SSCGxscjbAiLoeDXWeEzu"
    "nB/hIpxjVH6MTl4Pw4YSKnZ2NsIc3h81rA5lgdAbguUkV1y/lZ7d/cXGWEbf8yL00frvsD"
    "kAnfZdnlbnOHVMu0TaoSV6QUaBG4o7usZoiwF2XQ3mEGmVyGZwe7yjP/4nzh5RUZCsD1lW"
    "Q4aVBNBuSwN+HYl5WyMYVao1RMLKQGC0XpRd5SL7LMdt6Kjl18B0sCSvayqbtXln3HLtPM"
    "Tt6UqzakhO+nTeiqdtLOOkd6aLfHQ+v6BBBCToYURPppkw9GhMEE0E4PbXcuj1e3wuPVLX"
    "q8Yh8LfkaEmIZY4hQPvKCHplEJmatw0EjzQ5ofUkuV5seudGxxs/MoukAwPCkHkwFKCSOc"
    "qVk0RCkXHtJYAt+MU8qNkkyk0h0M3LvLi/tNJWcByQ/Bygrf7nuIV12q7b5kcUaafdtj9u"
    "2ayVJPfaYG2M7rJnL1e36DBLVdCrLhCTkiS5wF3E4W/NaBBJhvgn1IRRnkYneUxSAKgTPV"
    "VDgd0iDpbJCFTQUm5oZkTrSVtPQWTILUcaA7SGAU2yo67DKoHaRNuv62wkMUuv4akiMel5"
    "rm2OipKtTlJnq64PXbG+pdOob5bBq+Zik62+0uQisvJp2aYL9mtr8r7pAnDpeWf8Msf1cj"
    "rNyyoC80DdpBwU+wJbabUtS+nTb+6jf1akvhn9rGWm37/VHVo4gXGl695V8KJgsaLLHrH/"
    "aJLrbhYgoimV+Ced+2NSKU0JeCtGT/tXULlIghlaAxgglfdGRz0XKQLz7IgRP2OCKKR4Jo"
    "yRDPL9PMtUpTsUiT1zzGCBnMUFMpyAURaVEAtoTQdcuMN3YcLc+vemPD0V1Jr9Lh5SaYN5"
    "OVf+VpTEuGZd0xuIlLXHz36wS1gqlqEWK3YaZChGAiVlotQUja5Q6uu7iRjVxZ2NKVBRlU"
    "vHUdK3dw3Zo1+2Y5hhePxk6zUmRTOCL7Ine5xrL4Zkg2Z7g0acuMW+z6lkaqqoLnm+xVLQ"
    "C7YWPBuuCdnjIOyu841Hr9XvOekKHoJjX/Qo4SX0nxfDLWdDgDv9MpUlx/ZJl6uPRraY4B"
    "vaW48JbFheKVXn3oDJ3Hx9Bx/q9hIJaHncdHheAXT9EIUt4R9F0yXpXRa3A5VgbL8C048P"
    "hIUHwaYH/g0T+GDjJM5iqDmyNlbJmup5hUoRgaQ8/5mgUNPcyOwWM+m8/IU8Y+9eFm+tQn"
    "zr7SU6amYcD7wFMMHaAaHgX+wSVs4B6ueg5gDy7H/EcsbAYuOLKw/uSFTwc9PqNiTLCtjB"
    "A8z9CZPashV9CbuIIu6klcyoHYrNmqFg9i/IGIeMDSmHYmoddQ5DKUkHwaB45vFzQBzsLk"
    "egdqJ5S1xU+84yFknCvsJwhXEPjnSiD2nRBwrqSAG19jcE3HEU6wnoFk0bssneG8KkjnDC"
    "TpzEsFQlVMuHmbpaszWdBO5oSsf/veRpn2q8gGkV7NrXB+Sa/mlnZswasps5GW98utfxuX"
    "jRG3xC4uXwb3yueHq6tNeeHugM4rVt33AvsO5e9hUmizV+WHSxUM1sP2NRTL+60TGb0v0L"
    "nwZcMYIrTz+zIOob45KVUDud80R/2L+n6j9nWo/v3Q7R4dve8eHJ2enRy/f39ydpDogcVT"
    "VQph//IT0wkzgjhWEst9Q4JujLXvL7HSYL3u2TyWdPes3JRm57IqY2ZcC43VPHJ9Rkt7Bm"
    "569cjn5WNU1ArwuckY22sLNiQ/8AuiNHzVwvwUn6qclryw0QYLt25SJq7Xq7vCKjPlU8yz"
    "Zvkcv0T5+kMCaMs0s+4FiBSRAuM0i1qjzzy6dkNT/SYE+64IjwmgLcOz7lBm02MbDRHE03"
    "+qXOAZnPSC5wrTSI/VVnqs4t4ZCekYWVQrUyi6JyfziO6Tk3LZzc41Rs/tIWLq0w5HzY3O"
    "VGq52qxNY6pUbpFXZclFtQplFhGPG79Y/u2mIO3UGFb25WYrOgkpXVHzdhJYSzHP0hIV5S"
    "lM5SUq1pblXJuhtbJ0pY1OL9/+D8E+d2E="
)
