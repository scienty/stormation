from inventory import scan
import os

def main():
    import os, json
    from common.objecthelper import json_encoder
    config_path = os.path.join(os.path.dirname(__file__),
                               'skew.yml')

    os.environ["SKEW_CONFIG"] = config_path

    credential_path = os.path.join('~/', '.aws',
                                   'config')


    #os.environ['AWS_CONFIG_FILE'] = credential_path
    region = 'us-east-1'
    profile = 'west1'

    arn = scan('arn:aws:ec2:us-east-1:1234567890:instance/*', profile=profile)
    for resource in arn:
        print(json.dumps(resource.data, default=json_encoder))



if __name__ == '__main__':
    main()